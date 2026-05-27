"""CRMNext Oracle DB integration routes.

Provides two endpoints for MASHUPCONNECTION:
  GET  /api/crm/mashup/preview/{tp_id}  — preview (no DB change)
  POST /api/crm/mashup/insert/{tp_id}   — idempotent insert

Idempotency rule:
  - First push: generate new CONNECTIONID, insert row, store
    connection_id in SDGNext PostgreSQL (technical_details.crmConnectionId)
  - Subsequent push: read stored crmConnectionId from PostgreSQL,
    delete old Oracle row, re-insert with SAME CONNECTIONID
  MASHUPIDLIST.LASTID is incremented ONLY on first push.

Why PostgreSQL-based lookup (not Oracle DESCRIPTION search):
  The CRMNext Oracle DB has application triggers/logic that may modify
  the DESCRIPTION column on INSERT, stripping any embedded markers.
  Storing the mapping in SDGNext's own DB is fully within our control.
"""

import os
import oracledb
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.core.database import get_db
from app.core.oracle_db import get_oracle_connection, get_oracle_schema
from app.models.domain import (
    IntegrationTouchpoint, IDRTechnical,
    IDRFunctional, IDRActionLog
)

router = APIRouter()

OWNER_ID = 914
ITEM_ID = 1
DS_ITEM_ID = 2  # MashupIdList ITEMID for DATASOURCEID (separate from CONNECTIONID)
FIELD_ITEM_ID = 3  # MashupIdList ITEMID for FIELDID (MASHUPDATASOURCEFIELD, separate counter)


def _get_tp_data(tp_id: int, db: Session):
    """Resolve touchpoint + related rows."""
    tp = db.query(IntegrationTouchpoint).filter(
        IntegrationTouchpoint.id == tp_id
    ).first()
    if not tp:
        raise HTTPException(status_code=404,
                            detail="Touchpoint not found")
    tech = db.query(IDRTechnical).filter(
        IDRTechnical.touchpoint_id == tp_id
    ).first()
    func = db.query(IDRFunctional).filter(
        IDRFunctional.touchpoint_id == tp_id
    ).first()
    return tp, tech, func


def _get_api_name(tech, tp):
    """Extract apiName from technical_details or fall back to tp.name."""
    td = {}
    if tech and tech.technical_details:
        td = (tech.technical_details
              if isinstance(tech.technical_details, dict) else {})
    return (td.get("apiName") or "").strip() or (tp.name or "").strip()


def _get_stored_connection_id(tech):
    """Read previously-assigned CRM CONNECTIONID from SDGNext PostgreSQL.

    Returns int or None. This is the PRIMARY idempotency source —
    fully within our control, immune to Oracle triggers/column quirks.
    """
    if not tech or not tech.technical_details:
        return None
    td = tech.technical_details if isinstance(tech.technical_details, dict) else {}
    cid = td.get("crmConnectionId")
    if cid is not None:
        try:
            return int(cid)
        except (ValueError, TypeError):
            return None
    return None


def _save_connection_id(db: Session, tech, connection_id: int):
    """Persist the CRM CONNECTIONID into technical_details JSON.

    This is what makes subsequent pushes idempotent — we read this
    value back on the next push to know which Oracle row to update.
    """
    if not tech:
        return
    td = dict(tech.technical_details or {})
    td["crmConnectionId"] = connection_id
    tech.technical_details = td
    flag_modified(tech, "technical_details")


def _find_shared_connection_id(db: Session, current_tp_id: int, uat_url: str):
    """Find if any OTHER touchpoint already has a crmConnectionId for
    the same UAT URL. This handles the scenario where multiple
    touchpoints share the same endpoint (same source system).

    Returns int (shared connection_id) or None.
    """
    if not uat_url:
        return None

    # Query all IDRTechnical rows except the current touchpoint
    all_techs = db.query(IDRTechnical).filter(
        IDRTechnical.touchpoint_id != current_tp_id
    ).all()

    for other_tech in all_techs:
        td = other_tech.technical_details
        if not td or not isinstance(td, dict):
            continue
        other_url = (td.get("uatUrl") or "").strip()
        other_cid = td.get("crmConnectionId")
        if other_url == uat_url and other_cid is not None:
            try:
                return int(other_cid)
            except (ValueError, TypeError):
                continue

    return None


def _get_stored_datasource_id(tech):
    """Read previously-assigned CRM DATASOURCEID from SDGNext PostgreSQL.

    Returns int or None. Mirrors _get_stored_connection_id but for
    the MASHUPDATASOURCE table.
    """
    if not tech or not tech.technical_details:
        return None
    td = tech.technical_details if isinstance(tech.technical_details, dict) else {}
    dsid = td.get("crmDatasourceId")
    if dsid is not None:
        try:
            return int(dsid)
        except (ValueError, TypeError):
            return None
    return None


def _save_datasource_id(db: Session, tech, datasource_id: int):
    """Persist the CRM DATASOURCEID into technical_details JSON.

    Mirrors _save_connection_id but for MASHUPDATASOURCE.
    """
    if not tech:
        return
    td = dict(tech.technical_details or {})
    td["crmDatasourceId"] = datasource_id
    tech.technical_details = td
    flag_modified(tech, "technical_details")


def _ds_row_exists(cursor, schema, datasource_id: int) -> bool:
    """Check if MASHUPDATASOURCE row exists for this DATASOURCEID."""
    cursor.execute(
        f"SELECT 1 FROM {schema}.MASHUPDATASOURCE "
        f"WHERE OWNERID = :owner AND DATASOURCEID = :dsid",
        {"owner": OWNER_ID, "dsid": datasource_id}
    )
    return cursor.fetchone() is not None


def _verify_oracle_row_exists(cursor, schema, connection_id):
    """Check if the CONNECTIONID still exists in Oracle (guard against
    manual deletions on the Oracle side)."""
    cursor.execute(
        f"SELECT 1 FROM {schema}.MASHUPCONNECTION "
        f"WHERE OWNERID = :owner AND CONNECTIONID = :cid",
        {"owner": OWNER_ID, "cid": connection_id}
    )
    return cursor.fetchone() is not None


def _build_preview_dict(connection_id, api_name, is_update):
    """Build the preview dict shown in the modal."""
    return {
        "OWNERID": OWNER_ID,
        "CONNECTIONID": connection_id,
        "NAME": api_name,
        "DESCRIPTION": api_name,
        "TYPE": 10,
        "TIMEOUT": 0,
        "ISENABLED": 1,
        "CREATEDBY": "1",
        "CREATEDON": "SYSDATE",
        "LASTMODIFIEDBY": "1",
        "LASTMODIFIEDON": "SYSDATE",
        "ISFRESHCONNECTION": 0,
        "PROXYID": None,
        "ENCRYPTIONTYPE": -1,
        "USEENCRYPTION": 0,
        "PUBLICKEY": None,
        "KEYSIZE": -1,
        "is_update": is_update,
    }


def _do_insert(cursor, schema, connection_id, api_name, tp_id):
    """Execute the MASHUPCONNECTION INSERT."""
    description = api_name
    cursor.execute(
        f"""INSERT INTO {schema}.MASHUPCONNECTION (
            OWNERID, CONNECTIONID, NAME, DESCRIPTION,
            TYPE, TIMEOUT, ISENABLED,
            CREATEDBY, CREATEDON,
            LASTMODIFIEDBY, LASTMODIFIEDON,
            ISFRESHCONNECTION, PROXYID,
            ENCRYPTIONTYPE, USEENCRYPTION,
            PUBLICKEY, KEYSIZE
        ) VALUES (
            :ownerid, :connectionid, :name, :description,
            :type, :timeout, :isenabled,
            :createdby, SYSDATE,
            :lastmodifiedby, SYSDATE,
            :isfreshconnection, NULL,
            :encryptiontype, :useencryption,
            NULL, :keysize
        )""",
        {
            "ownerid": OWNER_ID,
            "connectionid": connection_id,
            "name": api_name,
            "description": description,
            "type": 10,
            "timeout": 0,
            "isenabled": 1,
            "createdby": "1",
            "lastmodifiedby": "1",
            "isfreshconnection": 0,
            "encryptiontype": -1,
            "useencryption": 0,
            "keysize": -1,
        }
    )


@router.get("/api/crm/mashup/preview/{tp_id}")
def crm_mashup_preview(tp_id: int, db: Session = Depends(get_db)):
    """Preview what will be inserted. Does NOT modify Oracle."""
    tp, tech, func = _get_tp_data(tp_id, db)

    api_name = _get_api_name(tech, tp)
    if not api_name:
        raise HTTPException(
            status_code=400,
            detail=(
                "API Name is empty. Fill in the API Name field in "
                "Technical Details before pushing to CRM."
            )
        )

    # PRIMARY CHECK: Do we already have a stored connection_id in PostgreSQL?
    stored_cid = _get_stored_connection_id(tech)

    if stored_cid:
        # Verify the row still exists in Oracle (guard against manual deletes)
        conn = None
        try:
            conn = get_oracle_connection()
            cursor = conn.cursor()
            if _verify_oracle_row_exists(cursor, get_oracle_schema(), stored_cid):
                return {
                    "tp_id": tp_id,
                    "tp_name": tp.name,
                    "api_name": api_name,
                    "is_update": True,
                    "preview": _build_preview_dict(stored_cid, api_name, True)
                }
            # Row was deleted from Oracle manually — treat as fresh insert
        except Exception:
            # If Oracle is unreachable, still trust our stored ID
            return {
                "tp_id": tp_id,
                "tp_name": tp.name,
                "api_name": api_name,
                "is_update": True,
                "preview": _build_preview_dict(stored_cid, api_name, True)
            }
        finally:
            if conn:
                conn.close()

    # No stored ID — first push. Preview the next CONNECTIONID.
    schema = get_oracle_schema()
    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()

        cursor.execute(
            f"SELECT LASTID FROM {schema}.MASHUPIDLIST "
            f"WHERE OWNERID = :owner AND ITEMID = :item",
            {"owner": OWNER_ID, "item": ITEM_ID}
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"No row in MASHUPIDLIST for "
                    f"OWNERID={OWNER_ID}, ITEMID={ITEM_ID}"
                )
            )
        connection_id = int(row[0]) + 1

        return {
            "tp_id": tp_id,
            "tp_name": tp.name,
            "api_name": api_name,
            "is_update": False,
            "preview": _build_preview_dict(connection_id, api_name, False)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Oracle error during preview: {e}"
        )
    finally:
        if conn:
            conn.close()


@router.post("/api/crm/mashup/insert/{tp_id}")
def crm_mashup_insert(tp_id: int, db: Session = Depends(get_db)):
    """Idempotent insert into MASHUPCONNECTION.

    First push:
      - Atomically increments LASTID in MASHUPIDLIST
      - Inserts new MASHUPCONNECTION row
      - Stores connection_id in SDGNext PostgreSQL for future lookups

    Subsequent push (same touchpoint):
      - Reads stored crmConnectionId from PostgreSQL
      - Deletes old Oracle row
      - Re-inserts with SAME CONNECTIONID and updated data
      - LASTID is NOT incremented again
    """
    tp, tech, func = _get_tp_data(tp_id, db)

    api_name = _get_api_name(tech, tp)
    if not api_name:
        raise HTTPException(
            status_code=400,
            detail=(
                "API Name is empty. Fill in the API Name field in "
                "Technical Details before pushing to CRM."
            )
                )

    # PRIMARY CHECK: stored connection_id in our PostgreSQL
    stored_cid = _get_stored_connection_id(tech)

    # SHARED CONNECTION CHECK: if no stored_cid for this touchpoint,
    # check if another touchpoint with the same UAT URL already has one.
    td = tech.technical_details if (tech and isinstance(tech.technical_details, dict)) else {}
    uat_url = (td.get("uatUrl") or "").strip()
    shared_cid = None
    if not stored_cid and uat_url:
        shared_cid = _find_shared_connection_id(db, tp_id, uat_url)

    schema = get_oracle_schema()
    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()

        if stored_cid:
            # UPDATE path: we know the CONNECTIONID from our own DB
            connection_id = stored_cid
            is_update = True

            # Delete child first (FK_MASHUPWEBSERVICECONNECTION constraint)
            cursor.execute(
                f"DELETE FROM {schema}.MASHUPWSCONNECTION "
                f"WHERE OWNERID = :owner AND CONNECTIONID = :cid",
                {"owner": OWNER_ID, "cid": connection_id}
            )
            # Then delete parent (safe even if row was already deleted)
            cursor.execute(
                f"DELETE FROM {schema}.MASHUPCONNECTION "
                f"WHERE OWNERID = :owner AND CONNECTIONID = :cid",
                {"owner": OWNER_ID, "cid": connection_id}
            )
            _do_insert(cursor, schema, connection_id, api_name, tp_id)

        elif shared_cid:
            # SHARED path: another touchpoint already created this connection.
            # Reuse the same CONNECTIONID. Update Oracle row with current data.
            connection_id = shared_cid
            is_update = True

            # Delete child first (FK constraint)
            cursor.execute(
                f"DELETE FROM {schema}.MASHUPWSCONNECTION "
                f"WHERE OWNERID = :owner AND CONNECTIONID = :cid",
                {"owner": OWNER_ID, "cid": connection_id}
            )
            # Delete parent
            cursor.execute(
                f"DELETE FROM {schema}.MASHUPCONNECTION "
                f"WHERE OWNERID = :owner AND CONNECTIONID = :cid",
                {"owner": OWNER_ID, "cid": connection_id}
            )
            _do_insert(cursor, schema, connection_id, api_name, tp_id)

        else:
            # INSERT path: first push — atomically get new ID
            is_update = False
            new_id_var = cursor.var(oracledb.NUMBER)
            cursor.execute(
                f"UPDATE {schema}.MASHUPIDLIST "
                f"SET LASTID = LASTID + 1 "
                f"WHERE OWNERID = :owner AND ITEMID = :item "
                f"RETURNING LASTID INTO :new_id",
                {
                    "owner": OWNER_ID,
                    "item": ITEM_ID,
                    "new_id": new_id_var
                }
            )
            connection_id = int(new_id_var.getvalue()[0])
            _do_insert(cursor, schema, connection_id, api_name, tp_id)

        conn.commit()

        # --- POST-COMMIT: Store connection_id in SDGNext PostgreSQL ---
        _save_connection_id(db, tech, connection_id)

        # Action log for audit trail
        action = "updated" if is_update else "created"
        db.add(IDRActionLog(
            touchpoint_id=tp_id,
            action_type="Manual Update",
            action_by="User",
            comment=(
                f"CRM MASHUPCONNECTION {action}. "
                f"CONNECTIONID={connection_id}, NAME={api_name}"
            )
        ))
        db.commit()

        return {
            "success": True,
            "connection_id": connection_id,
            "name": api_name,
            "is_update": is_update,
            "message": (
                f"MASHUPCONNECTION {'updated' if is_update else 'created'} "
                f"successfully. CONNECTIONID = {connection_id}"
            )
        }

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise HTTPException(
            status_code=500,
            detail=f"Oracle error during insert: {e}"
        )
    finally:
        if conn:
            conn.close()


# ============================================================
# MASHUPWSCONNECTION — Web Service Connection
# ============================================================

SERVICEXML_TEMPLATE = """<webService xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
<id xmlns="www.crmnext.com/biznext/service">{connection_id}</id>
<connectionTimeout xmlns="www.crmnext.com/biznext/service">0</connectionTimeout>
<IsFreshConnection xmlns="www.crmnext.com/biznext/service">true</IsFreshConnection>
<IsHistory xmlns="www.crmnext.com/biznext/service">false</IsHistory>
<historyid xmlns="www.crmnext.com/biznext/service">-1</historyid>
<ProxyID xmlns="www.crmnext.com/biznext/service">0</ProxyID>
<UseEncryption xmlns="www.crmnext.com/biznext/service">false</UseEncryption>
<EncryptionType xmlns="www.crmnext.com/biznext/service">0</EncryptionType>
<IVMode xmlns="www.crmnext.com/biznext/service">Prior16Bytes</IVMode>
<CipherMode xmlns="www.crmnext.com/biznext/service">CBC</CipherMode>
<KeySize xmlns="www.crmnext.com/biznext/service">0</KeySize>
<name xmlns="www.crmnext.com/biznext/service"> </name>
<serviceLocation xmlns="www.crmnext.com/biznext/service">{service_location}</serviceLocation>
<wsdlLocation xmlns="www.crmnext.com/biznext/service"> </wsdlLocation>
<protocol xmlns="www.crmnext.com/biznext/service" />
<isWcfClient xmlns="www.crmnext.com/biznext/service">false</isWcfClient>
<isSilverlight xmlns="www.crmnext.com/biznext/service">false</isSilverlight>
<HeaderVariablesXml xmlns="www.crmnext.com/biznext/service">{header_xml_escaped}</HeaderVariablesXml>
</webService>"""


def _build_servicexml(connection_id: int, service_location: str, header_xml_escaped: str) -> str:
    """Assemble the full SERVICEXML from template + escaped headers."""
    return SERVICEXML_TEMPLATE.format(
        connection_id=connection_id,
        service_location=service_location,
        header_xml_escaped=header_xml_escaped
    )


def _ws_row_exists(cursor, schema, connection_id: int) -> bool:
    """Check if MASHUPWSCONNECTION row exists for this CONNECTIONID."""
    cursor.execute(
        f"SELECT 1 FROM {schema}.MASHUPWSCONNECTION "
        f"WHERE OWNERID = :owner AND CONNECTIONID = :cid",
        {"owner": OWNER_ID, "cid": connection_id}
    )
    return cursor.fetchone() is not None


def _do_ws_insert(cursor, schema, connection_id: int, service_name: str,
                  service_location: str, service_xml: str,
                  request_header_key_xml: str):
    """Execute the MASHUPWSCONNECTION INSERT."""
    cursor.execute(
        f"""INSERT INTO {schema}.MASHUPWSCONNECTION (
            OWNERID, CONNECTIONID, SERVICENAME, SERVICELOCATION,
            WSDLLOCATION, SERVICEXML, ISWCFSERVICE, ISSILVERLIGHTCLIENT,
            USERID, PASSWORD, SETTINGXML, ASSEMBLYNAME,
            CLASSNAME, USEREFLECTION, REQUESTHEADERKEYXML,
            PASSWORDSTORAGEID
        ) VALUES (
            :ownerid, :connectionid, :servicename, :servicelocation,
            :wsdllocation, :servicexml, :iswcfservice, :issilverlightclient,
            :userid, :password, NULL, NULL,
            NULL, :usereflection, :requestheaderkeyxml,
            NULL
        )""",
        {
            "ownerid": OWNER_ID,
            "connectionid": connection_id,
            "servicename": service_name,
            "servicelocation": service_location,
            "wsdllocation": " ",
            "servicexml": service_xml,
            "iswcfservice": 0,
            "issilverlightclient": 0,
            "userid": "imhkV5ov3MM=",
            "password": "imhkV5ov3MM=",
            "usereflection": 0,
            "requestheaderkeyxml": request_header_key_xml,
        }
    )


@router.get("/api/crm/mashupws/preview/{tp_id}")
def crm_mashupws_preview(tp_id: int, db: Session = Depends(get_db)):
    """Preview what will be inserted into MASHUPWSCONNECTION.

    Validates that MASHUPCONNECTION was already pushed (crmConnectionId
    must exist). Generates SERVICEXML and REQUESTHEADERKEYXML via AI.
    """
    from app.core.ai_agent import generate_crm_headers_xml

    tp, tech, func = _get_tp_data(tp_id, db)

    # Validate: crmConnectionId must exist
    stored_cid = _get_stored_connection_id(tech)
    if not stored_cid:
        raise HTTPException(
            status_code=400,
            detail=(
                "Push MASHUPCONNECTION first. The \"Push to CRM\" button "
                "must be used before pushing the WS connection."
            )
        )

    # Validate: apiName
    api_name = _get_api_name(tech, tp)
    if not api_name:
        raise HTTPException(
            status_code=400,
            detail="API Name is empty. Fill in the API Name field first."
        )

    # Validate: uatUrl
    td = tech.technical_details if (tech and isinstance(tech.technical_details, dict)) else {}
    service_location = (td.get("uatUrl") or "").strip()
    if not service_location:
        raise HTTPException(
            status_code=400,
            detail=(
                "UAT URL is required. Fill in the UAT URL in "
                "Connectivity tab before pushing WS connection."
            )
        )

    # Generate headers XML via AI
    mandatory_headers = (td.get("mandatoryHeaders") or "").strip()
    headers_result = generate_crm_headers_xml(
        mandatory_headers_str=mandatory_headers,
        service_location=service_location,
        api_name=api_name
    )

    # Assemble SERVICEXML
    service_xml = _build_servicexml(
        connection_id=stored_cid,
        service_location=service_location,
        header_xml_escaped=headers_result["header_variables_xml_escaped"]
    )
    request_header_key_xml = headers_result["header_variables_xml"]

    # Check if row already exists in Oracle (for is_update flag)
    is_update = False
    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()
        is_update = _ws_row_exists(cursor, get_oracle_schema(), stored_cid)
    except Exception:
        pass
    finally:
        if conn:
            conn.close()

    return {
        "tp_id": tp_id,
        "tp_name": tp.name,
        "connection_id": stored_cid,
        "is_update": is_update,
        "preview": {
            "OWNERID": OWNER_ID,
            "CONNECTIONID": stored_cid,
            "SERVICENAME": api_name,
            "SERVICELOCATION": service_location,
            "WSDLLOCATION": " ",
            "SERVICEXML": service_xml,
            "ISWCFSERVICE": 0,
            "ISSILVERLIGHTCLIENT": 0,
            "USERID": "imhkV5ov3MM=",
            "PASSWORD": "imhkV5ov3MM=",
            "USEREFLECTION": 0,
            "REQUESTHEADERKEYXML": request_header_key_xml,
        }
    }


@router.post("/api/crm/mashupws/insert/{tp_id}")
def crm_mashupws_insert(tp_id: int, db: Session = Depends(get_db)):
    """Idempotent insert into MASHUPWSCONNECTION.

    First push: INSERT row.
    Subsequent push: DELETE existing row, INSERT fresh.
    CONNECTIONID is always crmConnectionId from PostgreSQL.
    """
    from app.core.ai_agent import generate_crm_headers_xml

    tp, tech, func = _get_tp_data(tp_id, db)

    # Validate: crmConnectionId must exist
    stored_cid = _get_stored_connection_id(tech)
    if not stored_cid:
        raise HTTPException(
            status_code=400,
            detail=(
                "Push MASHUPCONNECTION first. The \"Push to CRM\" button "
                "must be used before pushing the WS connection."
            )
        )

    # Validate: apiName
    api_name = _get_api_name(tech, tp)
    if not api_name:
        raise HTTPException(
            status_code=400,
            detail="API Name is empty. Fill in the API Name field first."
        )

    # Validate: uatUrl
    td = tech.technical_details if (tech and isinstance(tech.technical_details, dict)) else {}
    service_location = (td.get("uatUrl") or "").strip()
    if not service_location:
        raise HTTPException(
            status_code=400,
            detail=(
                "UAT URL is required. Fill in the UAT URL in "
                "Connectivity tab before pushing WS connection."
            )
        )

    # Generate headers XML via AI
    mandatory_headers = (td.get("mandatoryHeaders") or "").strip()
    headers_result = generate_crm_headers_xml(
        mandatory_headers_str=mandatory_headers,
        service_location=service_location,
        api_name=api_name
    )

    # Assemble SERVICEXML
    service_xml = _build_servicexml(
        connection_id=stored_cid,
        service_location=service_location,
        header_xml_escaped=headers_result["header_variables_xml_escaped"]
    )
    request_header_key_xml = headers_result["header_variables_xml"]

    schema = get_oracle_schema()
    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()

        # Idempotency: check if row exists
        is_update = _ws_row_exists(cursor, schema, stored_cid)

        if is_update:
            # DELETE old row, then INSERT fresh
            cursor.execute(
                f"DELETE FROM {schema}.MASHUPWSCONNECTION "
                f"WHERE OWNERID = :owner AND CONNECTIONID = :cid",
                {"owner": OWNER_ID, "cid": stored_cid}
            )

        _do_ws_insert(
            cursor, schema, stored_cid, api_name,
            service_location, service_xml, request_header_key_xml
        )

        conn.commit()

        # Action log
        action = "updated" if is_update else "created"
        db.add(IDRActionLog(
            touchpoint_id=tp_id,
            action_type="Manual Update",
            action_by="User",
            comment=(
                f"CRM MASHUPWSCONNECTION {action}. "
                f"CONNECTIONID={stored_cid}"
            )
        ))
        db.commit()

        return {
            "success": True,
            "connection_id": stored_cid,
            "is_update": is_update,
            "message": (
                f"MASHUPWSCONNECTION {'updated' if is_update else 'created'} "
                f"successfully. CONNECTIONID = {stored_cid}"
            )
        }

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
                raise HTTPException(
            status_code=500,
            detail=f"Oracle error during WS insert: {e}"
        )
    finally:
        if conn:
            conn.close()


# ============================================================
# MASHUPDATASOURCE — External Data Source
# ============================================================

@router.post("/api/crm/datasource/insert/{tp_id}")
def crm_datasource_insert(
    tp_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    """Idempotent insert into MASHUPDATASOURCE + MASHUPDATASOURCEFIELD.

    First push: atomically increment MashupIdList (ITEMID=2),
    insert new row, store crmDatasourceId in PostgreSQL.
    Subsequent push: read stored crmDatasourceId, delete old
    rows, insert fresh with same DATASOURCEID and reused FIELDIDs.
    """
    tp, tech, func = _get_tp_data(tp_id, db)

    # Validate: crmConnectionId must exist
    stored_cid = _get_stored_connection_id(tech)
    if not stored_cid:
        raise HTTPException(
            status_code=400,
            detail=(
                "Push Connection first via API's Connection Save. "
                "MASHUPCONNECTION must exist before creating a datasource."
            )
        )

    # Extract payload fields
    name = (payload.get("name") or "").strip()
    source = (payload.get("source") or "").strip()
    xslt = (payload.get("xslt") or "").strip()
    data_xpath = (payload.get("data_xpath") or "response").strip()
    output_fields = payload.get("output_fields") or []

    if not name:
        raise HTTPException(status_code=400, detail="Touchpoint name is required.")
    if not source:
        raise HTTPException(status_code=400, detail="Endpoint URL is required.")

    # Check for stored datasource ID (idempotency)
    stored_dsid = _get_stored_datasource_id(tech)

    # Build cleaned output_fields list
    new_field_names = [str(fn).strip() for fn in output_fields if str(fn).strip()]

    schema = get_oracle_schema()
    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()

        # Map of existing field NAME → FIELDID (populated on update path)
        existing_field_map = {}

        if stored_dsid:
            # UPDATE path: reuse same DATASOURCEID
            datasource_id = stored_dsid
            is_update = _ds_row_exists(cursor, schema, stored_dsid)

            if is_update:
                # Query existing fields to build NAME → FIELDID map
                cursor.execute(
                    f"SELECT NAME, FIELDID FROM {schema}.MASHUPDATASOURCEFIELD "
                    f"WHERE OWNERID = :owner AND DATASOURCEID = :dsid",
                    {"owner": OWNER_ID, "dsid": datasource_id}
                )
                for row in cursor.fetchall():
                    existing_field_map[row[0]] = int(row[1])

                # Delete ALL child field rows first (will re-insert with same FIELDIDs)
                cursor.execute(
                    f"DELETE FROM {schema}.MASHUPDATASOURCEFIELD "
                    f"WHERE OWNERID = :owner AND DATASOURCEID = :dsid",
                    {"owner": OWNER_ID, "dsid": datasource_id}
                )
                # Then delete parent datasource row
                cursor.execute(
                    f"DELETE FROM {schema}.MASHUPDATASOURCE "
                    f"WHERE OWNERID = :owner AND DATASOURCEID = :dsid",
                    {"owner": OWNER_ID, "dsid": datasource_id}
                )
        else:
            # INSERT path: first push — atomically get new ID
            is_update = False
            new_id_var = cursor.var(oracledb.NUMBER)
            cursor.execute(
                f"UPDATE {schema}.MASHUPIDLIST "
                f"SET LASTID = LASTID + 1 "
                f"WHERE OWNERID = :owner AND ITEMID = :item "
                f"RETURNING LASTID INTO :new_id",
                {
                    "owner": OWNER_ID,
                    "item": DS_ITEM_ID,
                    "new_id": new_id_var
                }
            )
            datasource_id = int(new_id_var.getvalue()[0])

        # INSERT MASHUPDATASOURCE row
        cursor.execute(
            f"""INSERT INTO {schema}.MASHUPDATASOURCE (
                OWNERID, DATASOURCEID, CONNECTIONID, NAME,
                SOURCETYPE, SOURCE, RETURNTYPE, RETURNMODE,
                DATAXPATH, CREATEDBY, CREATEDON, LASTMODIFIEDBY, LASTMODIFIEDON,
                ERRORCODEPATH, ERRORSTRINGPATH, PRIMARYFIELD,
                ISUTCDATETIME, ERRORCODEFIELDID, ERRORMSGFIELDID,
                TRANSACTIONFIELD, SUCCESSCODE, INDEXPARAMETER,
                BATCHSIZE, TOTALCOUNTXPATH, BATCHPARAMETER,
                USERIDPARAMETER, CURRENTTIMEFIELD, INPUTDATETIMEFORMAT,
                ENABLELOGGING, RETENTIONPERIOD, INITIALSYMBOLS, RENAMESYMBOLS,
                DESCRIPTION, XSLT, XSLTREFERENCEFIELD,
                RESTINVOKEMETHOD, USEENCRYPTION, ENCRYPTIONKEY,
                RESTINPUTMODE, IMAGEHEIGHT, IMAGEWIDTH, IMAGEFORMAT,
                XSLTTAG, CHECKFORERROR, CURRENTRECORDCOUNTPATH,
                REPLYQUEUE, WAITINTERVAL, REMOTEQUEUEMANAGERNAME,
                STRINGMODE, LOGINIDFIELD, BRANCHCODEPARAMETER,
                BRANCHIDPARAMETER, BRANCHNAMEPARAMETER,
                IPADDRESSFIELD, EMPLOYEECODEFIELD, INPUTXSLT,
                PASSWORD, ISSECURITYENABLED, SERVICETYPEID,
                IGNOREHTMLENCODE, FAULTCODEXPATH, FAULTMESSAGEXPATH,
                FAULTXSLT, ENCODING, SKIPNODEEXCEPTION,
                PREVPAGETOKENXPATH, NEXTPAGETOKENXPATH,
                ADDITIONALSETTINGS, OUTPUTLOGXSLT, USEDBY,
                KAFKASOURCETYPE, EXCEPTIONMESSAGE, ADAPTERID,
                UNIQUEEDSNAME, ISAUDITENABLE, ISMETRICSENABLE,
                ENABLEDATASOURCEMATRIX, OWNERIDPARAMETER
            ) VALUES (
                :ownerid, :datasourceid, :connectionid, :name,
                0, :source, 13, 1,
                :dataxpath, '1', SYSDATE, '1', SYSDATE,
                NULL, NULL, '-1',
                1, -1, -1,
                NULL, NULL, NULL,
                0, NULL, NULL,
                NULL, NULL, NULL,
                1, 7, NULL, NULL,
                NULL, :xslt, NULL,
                2, 0, NULL,
                4, 0, 0, NULL,
                'root', 0, NULL,
                NULL, 0, NULL,
                0, NULL, NULL,
                NULL, NULL,
                NULL, NULL, NULL,
                NULL, NULL, NULL,
                0, NULL, NULL,
                NULL, NULL, NULL,
                NULL, NULL,
                NULL, NULL, 0,
                0, NULL, NULL,
                NULL, 0, 0,
                NULL, NULL
            )""",
            {
                "ownerid": OWNER_ID,
                "datasourceid": datasource_id,
                "connectionid": stored_cid,
                "name": name,
                "source": source,
                "dataxpath": data_xpath,
                "xslt": xslt,
            }
        )

        # INSERT MASHUPDATASOURCEFIELD rows
        # - Existing fields (same NAME): reuse their FIELDID, no increment
        # - New fields: generate new FIELDID from MashupIdList ITEMID=3
        fields_created = 0
        fields_reused = 0
        for field_name_clean in new_field_names:
            if field_name_clean in existing_field_map:
                # Reuse existing FIELDID
                field_id = existing_field_map[field_name_clean]
                fields_reused += 1
            else:
                # New field — atomically increment MashupIdList ITEMID=3
                field_id_var = cursor.var(oracledb.NUMBER)
                cursor.execute(
                    f"UPDATE {schema}.MASHUPIDLIST "
                    f"SET LASTID = LASTID + 1 "
                    f"WHERE OWNERID = :owner AND ITEMID = :item "
                    f"RETURNING LASTID INTO :new_id",
                    {
                        "owner": OWNER_ID,
                        "item": FIELD_ITEM_ID,
                        "new_id": field_id_var
                    }
                )
                field_id = int(field_id_var.getvalue()[0])
            cursor.execute(
                f"""INSERT INTO {schema}.MASHUPDATASOURCEFIELD (
                    OWNERID, FIELDID, DATASOURCEID,
                    NAME, LABEL, TYPE,
                    ISSEARCHABLE, ISFILTERABLE, ISDISPLAY,
                    XPATH, ADDEDBY, ADDEDON,
                    MASKSTARTPOS, MASKTOTALCHAR, MASKCHAR,
                    APPLYMASKONNEWEDIT, MASKFORMATID, EDSRESOLVERID,
                    GROUPID, PARENTGROUPID, MAXLENGTH,
                    ADDITIONALSETTINGS
                ) VALUES (
                    :ownerid, :fieldid, :datasourceid,
                    :name, :label, 'String',
                    0, 0, 0,
                    :xpath, '1', SYSDATE,
                    -1, -1, '*',
                    0, -1, -1,
                    0, 0, -1,
                    '{"MongoOutputFieldMode":3}'
                )""",
                {
                    "ownerid": OWNER_ID,
                    "fieldid": field_id,
                    "datasourceid": datasource_id,
                    "name": field_name_clean,
                    "label": field_name_clean,
                    "xpath": field_name_clean,
                }
            )
            fields_created += 1

        conn.commit()

        # Store datasource_id in PostgreSQL for idempotency
        _save_datasource_id(db, tech, datasource_id)

        # Action log
        action = "updated" if is_update else "created"
        new_fields = fields_created - fields_reused
        db.add(IDRActionLog(
            touchpoint_id=tp_id,
            action_type="Manual Update",
            action_by="User",
            comment=(
                f"CRM MASHUPDATASOURCE {action}. "
                f"DATASOURCEID={datasource_id}, CONNECTIONID={stored_cid}, "
                f"fields={fields_created} (reused={fields_reused}, new={new_fields})"
            )
        ))
        db.commit()

        return {
            "success": True,
            "datasource_id": datasource_id,
            "connection_id": stored_cid,
            "fields_created": fields_created,
            "fields_reused": fields_reused,
            "fields_new": new_fields,
            "is_update": is_update,
            "message": (
                f"MASHUPDATASOURCE {'updated' if is_update else 'created'} "
                f"successfully. DATASOURCEID = {datasource_id}, "
                f"{fields_created} fields mapped "
                f"({fields_reused} reused, {new_fields} new)."
            )
        }

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise HTTPException(
            status_code=500,
            detail=f"Oracle error during datasource insert: {e}"
        )
    finally:
        if conn:
            conn.close()