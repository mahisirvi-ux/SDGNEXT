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
from fastapi import APIRouter, Depends, HTTPException
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