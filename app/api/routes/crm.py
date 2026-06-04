"""CRM multi-DB integration routes.

Supports Oracle, SQL Server (pyodbc), and PostgreSQL (psycopg2).
DB type, credentials, and OWNERID are stored per-project in
Project.crm_db_config JSON.

Existing Oracle projects fall back to ORACLE_* env vars + OWNERID 914.
"""

import re
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.core.database import get_db
from app.core.crm_db import (
    get_crm_connection, get_crm_schema,
    now_sql, adapt_query, atomic_increment,
    get_crm_config_for_project, get_owner_id,
    DB_TYPE_ORACLE,
)
from app.models.domain import (
    IntegrationTouchpoint, IDRTechnical,
    IDRFunctional, IDRActionLog, Project,
)

router = APIRouter()

DEFAULT_OWNER_ID = 914      # legacy default (Oracle deployments)
ITEM_ID = 1                 # MashupIdList ITEMID for CONNECTIONID
DS_ITEM_ID = 2              # MashupIdList ITEMID for DATASOURCEID
FIELD_ITEM_ID = 3           # MashupIdList ITEMID for FIELDID
MOCK_SERVICE_LOCATION = "http://127.0.0.1:8000/mock-api"


# ============================================================
# SHARED HELPERS — data access
# ============================================================

def _get_tp_data(tp_id: int, db: Session):
    tp = db.query(IntegrationTouchpoint).filter(
        IntegrationTouchpoint.id == tp_id
    ).first()
    if not tp:
        raise HTTPException(status_code=404, detail="Touchpoint not found")
    tech = db.query(IDRTechnical).filter(IDRTechnical.touchpoint_id == tp_id).first()
    func = db.query(IDRFunctional).filter(IDRFunctional.touchpoint_id == tp_id).first()
    return tp, tech, func


def _get_crm_context(tp, db: Session):
    """Resolve CRM DB type, config, schema, and owner_id for the touchpoint's project.
    Returns: (db_type, crm_config, schema, owner_id)
    """
    project = db.query(Project).filter(Project.id == tp.project_id).first()
    if not project:
        return DB_TYPE_ORACLE, {}, "", DEFAULT_OWNER_ID
    db_type, config = get_crm_config_for_project(project)
    schema = get_crm_schema(db_type, config)
    owner_id = get_owner_id(config)
    return db_type, config, schema, owner_id


def _get_api_name(tech, tp):
    td = {}
    if tech and tech.technical_details:
        td = tech.technical_details if isinstance(tech.technical_details, dict) else {}
    return (td.get("apiName") or "").strip() or (tp.name or "").strip()


def _get_stored_connection_id(tech):
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
    if not tech:
        return
    td = dict(tech.technical_details or {})
    td["crmConnectionId"] = connection_id
    tech.technical_details = td
    flag_modified(tech, "technical_details")


def _find_shared_connection_id(db: Session, current_tp_id: int, uat_url: str):
    if not uat_url:
        return None
    all_techs = db.query(IDRTechnical).filter(
        IDRTechnical.touchpoint_id != current_tp_id
    ).all()
    for other_tech in all_techs:
        td = other_tech.technical_details
        if not td or not isinstance(td, dict):
            continue
        if (td.get("uatUrl") or "").strip() == uat_url and td.get("crmConnectionId") is not None:
            try:
                return int(td["crmConnectionId"])
            except (ValueError, TypeError):
                continue
    return None


def _get_stored_datasource_id(tech):
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
    if not tech:
        return
    td = dict(tech.technical_details or {})
    td["crmDatasourceId"] = datasource_id
    tech.technical_details = td
    flag_modified(tech, "technical_details")


# ============================================================
# SHARED HELPERS — existence checks (dialect-aware)
# ============================================================

def _verify_connection_exists(cursor, schema, db_type, owner_id, connection_id) -> bool:
    sql = (f"SELECT 1 FROM {schema}.MASHUPCONNECTION "
           f"WHERE OWNERID = :owner AND CONNECTIONID = :cid")
    sql, params = adapt_query(sql, {"owner": owner_id, "cid": connection_id}, db_type)
    cursor.execute(sql, params)
    return cursor.fetchone() is not None


def _ds_row_exists(cursor, schema, db_type, owner_id, datasource_id: int) -> bool:
    sql = (f"SELECT 1 FROM {schema}.MASHUPDATASOURCE "
           f"WHERE OWNERID = :owner AND DATASOURCEID = :dsid")
    sql, params = adapt_query(sql, {"owner": owner_id, "dsid": datasource_id}, db_type)
    cursor.execute(sql, params)
    return cursor.fetchone() is not None


def _ws_row_exists(cursor, schema, db_type, owner_id, connection_id: int) -> bool:
    sql = (f"SELECT 1 FROM {schema}.MASHUPWSCONNECTION "
           f"WHERE OWNERID = :owner AND CONNECTIONID = :cid")
    sql, params = adapt_query(sql, {"owner": owner_id, "cid": connection_id}, db_type)
    cursor.execute(sql, params)
    return cursor.fetchone() is not None


# ============================================================
# SHARED HELPERS — XML builders (no DB dependency)
# ============================================================

def _build_template_properties(template_str: str) -> str:
    fields = re.findall(r"##(\w+)##", template_str)
    seen = set()
    unique_fields = []
    for f in fields:
        f_lower = f.lower()
        if f_lower not in seen:
            seen.add(f_lower)
            unique_fields.append(f_lower)

    field_elements = ""
    for name in unique_fields:
        field_elements += (
            f'\t\t<field name="{name}" type="String" regx="" '
            f'errormessage="" label="" inputmode="0" '
            f'ismandatory="false" isconvertbase64="false" '
            f'contentname="" contenttype="" '
            f'useEncryption="false" '
            f'disableFieldLogging="false" '
            f'dateRangeInDays="0" toFieldName="" '
            f'filterDisplayMode="0" arraytemplateid="0" '
            f'arraytemplatename="" resolverID="" '
            f'resolverName="" maskFormatID="" '
            f'maskFormatName="" fieldValidation=\'\'/>\\n'
        )
    return (
        f"<templateproperties>\n"
        f"\t<fields>\n{field_elements}\t</fields>\n"
        f"</templateproperties>"
    )


def _build_mapping_xml(unique_fields: list) -> str:
    mapping_elements = ""
    for idx, name in enumerate(unique_fields, start=1):
        mapping_elements += (
            f"<mapping parametername='{name}' "
            f"mappedcolumn='InputParam{idx}' />\n"
        )
    return f"<mappings>\n{mapping_elements}</mappings>"


def _build_preview_dict(owner_id, connection_id, api_name, is_update, db_type=DB_TYPE_ORACLE):
    now = now_sql(db_type)
    return {
        "OWNERID": owner_id,
        "CONNECTIONID": connection_id,
        "NAME": api_name,
        "DESCRIPTION": api_name,
        "TYPE": 10,
        "TIMEOUT": 0,
        "ISENABLED": 1,
        "CREATEDBY": "1",
        "CREATEDON": now,
        "LASTMODIFIEDBY": "1",
        "LASTMODIFIEDON": now,
        "ISFRESHCONNECTION": 0,
        "PROXYID": None,
        "ENCRYPTIONTYPE": -1,
        "USEENCRYPTION": 0,
        "PUBLICKEY": None,
        "KEYSIZE": -1,
        "is_update": is_update,
    }


# ============================================================
# SHARED HELPERS — INSERT wrappers (dialect-aware)
# ============================================================

def _do_insert(cursor, schema, db_type, owner_id, connection_id, api_name):
    now = now_sql(db_type)
    sql = f"""INSERT INTO {schema}.MASHUPCONNECTION (
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
            :createdby, {now},
            :lastmodifiedby, {now},
            :isfreshconnection, NULL,
            :encryptiontype, :useencryption,
            NULL, :keysize
        )"""
    params = {
        "ownerid": owner_id, "connectionid": connection_id,
        "name": api_name, "description": api_name,
        "type": 10, "timeout": 0, "isenabled": 1,
        "createdby": "1", "lastmodifiedby": "1",
        "isfreshconnection": 0, "encryptiontype": -1,
        "useencryption": 0, "keysize": -1,
    }
    sql, params = adapt_query(sql, params, db_type)
    cursor.execute(sql, params)


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


def _build_servicexml(connection_id, service_location, header_xml_escaped):
    return SERVICEXML_TEMPLATE.format(
        connection_id=connection_id,
        service_location=service_location,
        header_xml_escaped=header_xml_escaped,
    )


def _do_ws_insert(cursor, schema, db_type, owner_id, connection_id, service_name,
                  service_location, service_xml, request_header_key_xml):
    oracle_extra_col = ", PASSWORDSTORAGEID" if db_type == DB_TYPE_ORACLE else ""
    oracle_extra_val = ", NULL"              if db_type == DB_TYPE_ORACLE else ""

    sql = f"""INSERT INTO {schema}.MASHUPWSCONNECTION (
            OWNERID, CONNECTIONID, SERVICENAME, SERVICELOCATION,
            WSDLLOCATION, SERVICEXML, ISWCFSERVICE, ISSILVERLIGHTCLIENT,
            USERID, PASSWORD, SETTINGXML, ASSEMBLYNAME,
            CLASSNAME, USEREFLECTION, REQUESTHEADERKEYXML{oracle_extra_col}
        ) VALUES (
            :ownerid, :connectionid, :servicename, :servicelocation,
            :wsdllocation, :servicexml, :iswcfservice, :issilverlightclient,
            :userid, :password, NULL, NULL,
            NULL, :usereflection, :requestheaderkeyxml{oracle_extra_val}
        )"""
    params = {
        "ownerid": owner_id, "connectionid": connection_id,
        "servicename": service_name, "servicelocation": service_location,
        "wsdllocation": " ", "servicexml": service_xml,
        "iswcfservice": 0, "issilverlightclient": 0,
        "userid": "imhkV5ov3MM=", "password": "imhkV5ov3MM=",
        "usereflection": 0, "requestheaderkeyxml": request_header_key_xml,
    }
    sql, params = adapt_query(sql, params, db_type)
    cursor.execute(sql, params)


def _do_datasource_insert(cursor, schema, db_type, owner_id,
                          datasource_id, stored_cid, name,
                          source, data_xpath, xslt):
    now = now_sql(db_type)
    common_cols = """OWNERID, DATASOURCEID, CONNECTIONID, NAME,
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
            PREVPAGETOKENXPATH, NEXTPAGETOKENXPATH"""

    common_vals = f""":ownerid, :datasourceid, :connectionid, :name,
            0, :source, 13, 1,
            :dataxpath, '1', {now}, '1', {now},
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
            NULL, NULL"""

    if db_type == DB_TYPE_ORACLE:
        extra_cols = """,
            ADDITIONALSETTINGS, OUTPUTLOGXSLT, USEDBY,
            KAFKASOURCETYPE, EXCEPTIONMESSAGE, ADAPTERID,
            UNIQUEEDSNAME, ISAUDITENABLE, ISMETRICSENABLE,
            ENABLEDATASOURCEMATRIX, OWNERIDPARAMETER"""
        extra_vals = """,
            NULL, NULL, 0,
            0, NULL, NULL,
            NULL, 0, 0,
            NULL, NULL"""
    else:
        extra_cols = ""
        extra_vals = ""

    sql = f"""INSERT INTO {schema}.MASHUPDATASOURCE (
            {common_cols}{extra_cols}
        ) VALUES (
            {common_vals}{extra_vals}
        )"""
    params = {
        "ownerid": owner_id, "datasourceid": datasource_id,
        "connectionid": stored_cid, "name": name,
        "source": source, "dataxpath": data_xpath, "xslt": xslt,
    }
    sql, params = adapt_query(sql, params, db_type)
    cursor.execute(sql, params)


def _do_field_insert(cursor, schema, db_type, owner_id, field_id, datasource_id, field_name):
    now = now_sql(db_type)
    extra_col = ", ADDITIONALSETTINGS" if db_type == DB_TYPE_ORACLE else ""
    extra_val = ", :additionalsettings" if db_type == DB_TYPE_ORACLE else ""

    sql = f"""INSERT INTO {schema}.MASHUPDATASOURCEFIELD (
            OWNERID, FIELDID, DATASOURCEID,
            NAME, LABEL, TYPE,
            ISSEARCHABLE, ISFILTERABLE, ISDISPLAY,
            XPATH, ADDEDBY, ADDEDON,
            MASKSTARTPOS, MASKTOTALCHAR, MASKCHAR,
            APPLYMASKONNEWEDIT, MASKFORMATID, EDSRESOLVERID,
            GROUPID, PARENTGROUPID, MAXLENGTH{extra_col}
        ) VALUES (
            :ownerid, :fieldid, :datasourceid,
            :name, :label, 'String',
            0, 0, 0,
            :xpath, '1', {now},
            -1, -1, '*',
            0, -1, -1,
            0, 0, -1{extra_val}
        )"""
    params = {
        "ownerid": owner_id, "fieldid": field_id,
        "datasourceid": datasource_id, "name": field_name,
        "label": field_name, "xpath": field_name,
    }
    if db_type == DB_TYPE_ORACLE:
        params["additionalsettings"] = '{"MongoOutputFieldMode":3}'
    sql, params = adapt_query(sql, params, db_type)
    cursor.execute(sql, params)


# ============================================================
# MASHUPCONNECTION — routes
# ============================================================

@router.get("/api/crm/mashup/preview/{tp_id}")
def crm_mashup_preview(tp_id: int, db: Session = Depends(get_db)):
    tp, tech, func = _get_tp_data(tp_id, db)
    db_type, crm_config, schema, owner_id = _get_crm_context(tp, db)

    api_name = _get_api_name(tech, tp)
    if not api_name:
        raise HTTPException(status_code=400, detail="API Name is empty.")

    stored_cid = _get_stored_connection_id(tech)

    if stored_cid:
        conn = None
        try:
            conn = get_crm_connection(db_type, crm_config)
            cursor = conn.cursor()
            if _verify_connection_exists(cursor, schema, db_type, owner_id, stored_cid):
                return {
                    "tp_id": tp_id, "tp_name": tp.name,
                    "api_name": api_name, "is_update": True,
                    "preview": _build_preview_dict(owner_id, stored_cid, api_name, True, db_type),
                }
        except Exception:
            return {
                "tp_id": tp_id, "tp_name": tp.name,
                "api_name": api_name, "is_update": True,
                "preview": _build_preview_dict(owner_id, stored_cid, api_name, True, db_type),
            }
        finally:
            if conn:
                conn.close()

    conn = None
    try:
        conn = get_crm_connection(db_type, crm_config)
        cursor = conn.cursor()

        sql = (f"SELECT LASTID FROM {schema}.MASHUPIDLIST "
               f"WHERE OWNERID = :owner AND ITEMID = :item")
        sql, params = adapt_query(sql, {"owner": owner_id, "item": ITEM_ID}, db_type)
        cursor.execute(sql, params)
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=500,
                detail=f"No row in MASHUPIDLIST for OWNERID={owner_id}, ITEMID={ITEM_ID}",
            )
        connection_id = int(row[0]) + 1

        return {
            "tp_id": tp_id, "tp_name": tp.name,
            "api_name": api_name, "is_update": False,
            "preview": _build_preview_dict(owner_id, connection_id, api_name, False, db_type),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CRM DB error during preview: {e}")
    finally:
        if conn:
            conn.close()


@router.post("/api/crm/mashup/insert/{tp_id}")
def crm_mashup_insert(tp_id: int, db: Session = Depends(get_db)):
    tp, tech, func = _get_tp_data(tp_id, db)
    db_type, crm_config, schema, owner_id = _get_crm_context(tp, db)

    api_name = _get_api_name(tech, tp)
    if not api_name:
        raise HTTPException(status_code=400, detail="API Name is empty.")

    stored_cid = _get_stored_connection_id(tech)

    td = tech.technical_details if (tech and isinstance(tech.technical_details, dict)) else {}
    uat_url = (td.get("uatUrl") or "").strip()
    shared_cid = None
    if not stored_cid and uat_url:
        shared_cid = _find_shared_connection_id(db, tp_id, uat_url)

    conn = None
    try:
        conn = get_crm_connection(db_type, crm_config)
        cursor = conn.cursor()

        if stored_cid:
            connection_id = stored_cid
            is_update = True
            for tbl in ["MASHUPWSCONNECTION", "MASHUPCONNECTION"]:
                sql = (f"DELETE FROM {schema}.{tbl} "
                       f"WHERE OWNERID = :owner AND CONNECTIONID = :cid")
                s, p = adapt_query(sql, {"owner": owner_id, "cid": connection_id}, db_type)
                cursor.execute(s, p)
            _do_insert(cursor, schema, db_type, owner_id, connection_id, api_name)

        elif shared_cid:
            connection_id = shared_cid
            is_update = True
            for tbl in ["MASHUPWSCONNECTION", "MASHUPCONNECTION"]:
                sql = (f"DELETE FROM {schema}.{tbl} "
                       f"WHERE OWNERID = :owner AND CONNECTIONID = :cid")
                s, p = adapt_query(sql, {"owner": owner_id, "cid": connection_id}, db_type)
                cursor.execute(s, p)
            _do_insert(cursor, schema, db_type, owner_id, connection_id, api_name)

        else:
            is_update = False
            connection_id = atomic_increment(cursor, schema, db_type, owner_id, ITEM_ID)
            _do_insert(cursor, schema, db_type, owner_id, connection_id, api_name)

        conn.commit()
        _save_connection_id(db, tech, connection_id)

        action = "updated" if is_update else "created"
        db.add(IDRActionLog(
            touchpoint_id=tp_id, action_type="Manual Update", action_by="User",
            comment=f"CRM MASHUPCONNECTION {action}. CONNECTIONID={connection_id}, NAME={api_name}",
        ))
        db.commit()

        return {
            "success": True, "connection_id": connection_id,
            "name": api_name, "is_update": is_update,
            "message": f"MASHUPCONNECTION {'updated' if is_update else 'created'} successfully. CONNECTIONID = {connection_id}",
        }
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        raise HTTPException(status_code=500, detail=f"CRM DB error during insert: {e}")
    finally:
        if conn:
            conn.close()


# ============================================================
# MASHUPWSCONNECTION — routes
# ============================================================

@router.get("/api/crm/mashupws/preview/{tp_id}")
def crm_mashupws_preview(tp_id: int, db: Session = Depends(get_db)):
    from app.core.ai_agent import generate_crm_headers_xml

    tp, tech, func = _get_tp_data(tp_id, db)
    db_type, crm_config, schema, owner_id = _get_crm_context(tp, db)

    stored_cid = _get_stored_connection_id(tech)
    if not stored_cid:
        raise HTTPException(status_code=400, detail='Push MASHUPCONNECTION first.')

    api_name = _get_api_name(tech, tp)
    if not api_name:
        raise HTTPException(status_code=400, detail="API Name is empty.")

    service_location = MOCK_SERVICE_LOCATION
    td = tech.technical_details if (tech and isinstance(tech.technical_details, dict)) else {}
    mandatory_headers = (td.get("mandatoryHeaders") or "").strip()
    headers_result = generate_crm_headers_xml(mandatory_headers, service_location, api_name)

    service_xml = _build_servicexml(stored_cid, service_location,
                                    headers_result["header_variables_xml_escaped"])

    is_update = False
    conn = None
    try:
        conn = get_crm_connection(db_type, crm_config)
        cursor = conn.cursor()
        is_update = _ws_row_exists(cursor, schema, db_type, owner_id, stored_cid)
    except Exception:
        pass
    finally:
        if conn:
            conn.close()

    return {
        "tp_id": tp_id, "tp_name": tp.name,
        "connection_id": stored_cid, "is_update": is_update,
        "preview": {
            "OWNERID": owner_id, "CONNECTIONID": stored_cid,
            "SERVICENAME": api_name, "SERVICELOCATION": service_location,
            "WSDLLOCATION": " ", "SERVICEXML": service_xml,
            "ISWCFSERVICE": 0, "ISSILVERLIGHTCLIENT": 0,
            "USERID": "imhkV5ov3MM=", "PASSWORD": "imhkV5ov3MM=",
            "USEREFLECTION": 0,
            "REQUESTHEADERKEYXML": headers_result["header_variables_xml"],
        },
    }


@router.post("/api/crm/mashupws/insert/{tp_id}")
def crm_mashupws_insert(tp_id: int, db: Session = Depends(get_db)):
    from app.core.ai_agent import generate_crm_headers_xml

    tp, tech, func = _get_tp_data(tp_id, db)
    db_type, crm_config, schema, owner_id = _get_crm_context(tp, db)

    stored_cid = _get_stored_connection_id(tech)
    if not stored_cid:
        raise HTTPException(status_code=400, detail='Push MASHUPCONNECTION first.')

    api_name = _get_api_name(tech, tp)
    if not api_name:
        raise HTTPException(status_code=400, detail="API Name is empty.")

    service_location = MOCK_SERVICE_LOCATION
    td = tech.technical_details if (tech and isinstance(tech.technical_details, dict)) else {}
    mandatory_headers = (td.get("mandatoryHeaders") or "").strip()
    headers_result = generate_crm_headers_xml(mandatory_headers, service_location, api_name)

    service_xml = _build_servicexml(stored_cid, service_location,
                                    headers_result["header_variables_xml_escaped"])
    request_header_key_xml = headers_result["header_variables_xml"]

    conn = None
    try:
        conn = get_crm_connection(db_type, crm_config)
        cursor = conn.cursor()

        is_update = _ws_row_exists(cursor, schema, db_type, owner_id, stored_cid)
        if is_update:
            sql = (f"DELETE FROM {schema}.MASHUPWSCONNECTION "
                   f"WHERE OWNERID = :owner AND CONNECTIONID = :cid")
            s, p = adapt_query(sql, {"owner": owner_id, "cid": stored_cid}, db_type)
            cursor.execute(s, p)

        _do_ws_insert(cursor, schema, db_type, owner_id, stored_cid, api_name,
                      service_location, service_xml, request_header_key_xml)
        conn.commit()

        action = "updated" if is_update else "created"
        db.add(IDRActionLog(
            touchpoint_id=tp_id, action_type="Manual Update", action_by="User",
            comment=f"CRM MASHUPWSCONNECTION {action}. CONNECTIONID={stored_cid}",
        ))
        db.commit()

        return {
            "success": True, "connection_id": stored_cid, "is_update": is_update,
            "message": f"MASHUPWSCONNECTION {'updated' if is_update else 'created'} successfully. CONNECTIONID = {stored_cid}",
        }
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        raise HTTPException(status_code=500, detail=f"CRM DB error during WS insert: {e}")
    finally:
        if conn:
            conn.close()


# ============================================================
# MASHUPDATASOURCE — route
# ============================================================

@router.post("/api/crm/datasource/insert/{tp_id}")
def crm_datasource_insert(
    tp_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    tp, tech, func = _get_tp_data(tp_id, db)
    db_type, crm_config, schema, owner_id = _get_crm_context(tp, db)

    stored_cid = _get_stored_connection_id(tech)
    if not stored_cid:
        raise HTTPException(status_code=400, detail="Push Connection first.")

    name             = (payload.get("name")             or "").strip()
    source           = (payload.get("source")           or "").strip()
    xslt             = (payload.get("xslt")             or "").strip()
    data_xpath       = (payload.get("data_xpath")       or "response").strip()
    output_fields    = payload.get("output_fields")     or []
    request_template = (payload.get("request_template") or "")

    if not name:
        raise HTTPException(status_code=400, detail="Touchpoint name is required.")
    if not source:
        raise HTTPException(status_code=400, detail="Endpoint URL is required.")

    stored_dsid = _get_stored_datasource_id(tech)
    new_field_names = [str(fn).strip() for fn in output_fields if str(fn).strip()]

    conn = None
    try:
        conn = get_crm_connection(db_type, crm_config)
        cursor = conn.cursor()

        existing_field_map = {}

        if stored_dsid:
            datasource_id = stored_dsid
            is_update = _ds_row_exists(cursor, schema, db_type, owner_id, stored_dsid)

            if is_update:
                sql = (f"SELECT NAME, FIELDID FROM {schema}.MASHUPDATASOURCEFIELD "
                       f"WHERE OWNERID = :owner AND DATASOURCEID = :dsid")
                s, p = adapt_query(sql, {"owner": owner_id, "dsid": datasource_id}, db_type)
                cursor.execute(s, p)
                for row in cursor.fetchall():
                    existing_field_map[row[0]] = int(row[1])

                for tbl, col, val in [
                    ("MASHUPDATASOURCEFIELD",  "DATASOURCEID", datasource_id),
                    ("MASHUPQUERYPARAMETER",   "DATASOURCEID", datasource_id),
                    ("MASHUPPARAMMAPPING",     "DATASOURCEID", datasource_id),
                    ("MASHUPDATASOURCE",       "DATASOURCEID", datasource_id),
                ]:
                    extra = " AND NAME = 'Request'" if tbl == "MASHUPQUERYPARAMETER" else ""
                    sql = (f"DELETE FROM {schema}.{tbl} "
                           f"WHERE OWNERID = :owner AND {col} = :id{extra}")
                    s, pp = adapt_query(sql, {"owner": owner_id, "id": val}, db_type)
                    cursor.execute(s, pp)
        else:
            is_update = False
            datasource_id = atomic_increment(cursor, schema, db_type, owner_id, DS_ITEM_ID)

        _do_datasource_insert(cursor, schema, db_type, owner_id,
                              datasource_id, stored_cid, name,
                              source, data_xpath, xslt)

        fields_created = 0
        fields_reused = 0
        for field_name_clean in new_field_names:
            if field_name_clean in existing_field_map:
                field_id = existing_field_map[field_name_clean]
                fields_reused += 1
            else:
                field_id = atomic_increment(cursor, schema, db_type, owner_id, FIELD_ITEM_ID)
            _do_field_insert(cursor, schema, db_type, owner_id, field_id, datasource_id, field_name_clean)
            fields_created += 1

        # INSERT MASHUPQUERYPARAMETER
        now = now_sql(db_type)
        template_properties_xml = _build_template_properties(request_template)
        oracle_extra_col = ", PARENTID" if db_type == DB_TYPE_ORACLE else ""
        oracle_extra_val = ", 0"        if db_type == DB_TYPE_ORACLE else ""
        sql = f"""INSERT INTO {schema}.MASHUPQUERYPARAMETER (
                OWNERID, DATASOURCEID, NAME, TYPE,
                ISMANDATORY, ADDEDBY, ADDEDON,
                DISPLAYNAME, TEMPLATE,
                ISCOLLECTION, ISENUM, ISHEADERPROPERTY,
                TEMPLATEPROPERTIES, ARRAYTEMPLATEID{oracle_extra_col}
            ) VALUES (
                :ownerid, :datasourceid, 'Request', 'String',
                0, '1', {now},
                'Request', :template,
                0, 0, 0,
                :template_properties, 0{oracle_extra_val}
            )"""
        s, p = adapt_query(sql, {
            "ownerid": owner_id, "datasourceid": datasource_id,
            "template": request_template, "template_properties": template_properties_xml,
        }, db_type)
        cursor.execute(s, p)

        # INSERT MASHUPPARAMMAPPING
        template_fields = re.findall(r"##(\w+)##", request_template)
        seen_template = set()
        unique_template_fields = []
        for tf in template_fields:
            tf_lower = tf.lower()
            if tf_lower not in seen_template:
                seen_template.add(tf_lower)
                unique_template_fields.append(tf_lower)

        mapping_xml = _build_mapping_xml(unique_template_fields)
        sql = f"""INSERT INTO {schema}.MASHUPPARAMMAPPING (
                OWNERID, DATASOURCEID, CREATEDBY, CREATEDON, MAPPINGXML
            ) VALUES (
                :ownerid, :datasourceid, 1, {now}, :mapping_xml
            )"""
        s, p = adapt_query(sql, {
            "ownerid": owner_id, "datasourceid": datasource_id,
            "mapping_xml": mapping_xml,
        }, db_type)
        cursor.execute(s, p)

        conn.commit()
        _save_datasource_id(db, tech, datasource_id)

        action = "updated" if is_update else "created"
        new_fields = fields_created - fields_reused
        db.add(IDRActionLog(
            touchpoint_id=tp_id, action_type="Manual Update", action_by="User",
            comment=(
                f"CRM MASHUPDATASOURCE {action}. "
                f"DATASOURCEID={datasource_id}, CONNECTIONID={stored_cid}, "
                f"fields={fields_created} (reused={fields_reused}, new={new_fields})"
            ),
        ))
        db.commit()

        return {
            "success": True, "datasource_id": datasource_id,
            "connection_id": stored_cid,
            "fields_created": fields_created, "fields_reused": fields_reused,
            "fields_new": new_fields,
            "query_param_created": True, "param_mapping_created": True,
            "template_fields_count": len(unique_template_fields),
            "is_update": is_update,
            "message": (
                f"MASHUPDATASOURCE {'updated' if is_update else 'created'} successfully. "
                f"DATASOURCEID = {datasource_id}, {fields_created} fields mapped "
                f"({fields_reused} reused, {new_fields} new), "
                f"{len(unique_template_fields)} input params."
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        raise HTTPException(status_code=500, detail=f"CRM DB error during datasource insert: {e}")
    finally:
        if conn:
            conn.close()