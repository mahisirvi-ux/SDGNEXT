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
    get_crm_config_for_project, get_owner_id, get_project_short_name,
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
    """Resolve CRM DB type, config, schema, owner_id, and project short name
    for the touchpoint's project.
    Returns: (db_type, crm_config, schema, owner_id, project_short)
    """
    project = db.query(Project).filter(Project.id == tp.project_id).first()
    if not project:
        return DB_TYPE_ORACLE, {}, "", DEFAULT_OWNER_ID, ""
    db_type, config = get_crm_config_for_project(project)
    schema = get_crm_schema(db_type, config)
    owner_id = get_owner_id(config)
    project_short = get_project_short_name(config) or _derive_short_name(project.project_name)
    return db_type, config, schema, owner_id, project_short


# Words skipped when deriving an acronym from a bank/project name
_SHORTNAME_STOPWORDS = {"of", "and", "the", "for", "to", "in", "on", "at", "a", "an", "&"}


def _derive_short_name(full_name: str) -> str:
    """Derive a short acronym from a project/bank name.

        "State Bank of India"   -> "SBI"
        "Punjab National Bank"  -> "PNB"
        "HDFC Bank"             -> "HDFC"  (existing acronym token preferred)
        "ABC"                   -> "ABC"   (single token kept as-is)

    An explicit project_short_name in crm_db_config always overrides this.
    """
    name = (full_name or "").strip()
    if not name:
        return ""

    tokens = [t for t in re.split(r"[\s\-_]+", name) if t]

    # If the name already contains an acronym-like token (all caps, 2+ chars),
    # prefer the longest one (e.g. "HDFC Bank" -> "HDFC", "ICICI Bank" -> "ICICI").
    acronym_tokens = [t for t in tokens if len(t) >= 2 and t.isupper()]
    if acronym_tokens:
        return max(acronym_tokens, key=len)

    # Otherwise build an acronym from the initials of significant words.
    significant = [t for t in tokens if t.lower() not in _SHORTNAME_STOPWORDS]
    if len(significant) <= 1:
        return name  # single meaningful word — already short
    return "".join(t[0].upper() for t in significant)


def _build_connection_naming(project_short, source_system, fallback_name):
    """Build (NAME, DESCRIPTION) for a MASHUPCONNECTION.

    NAME        = "{project_short} {source_system} Connection"   e.g. "SBI CBS Connection"
    DESCRIPTION = "Integration connection for {project_short} {source_system} source system"

    Falls back gracefully when project_short or source_system is missing.
    """
    short = (project_short or "").strip()
    src = (source_system or "").strip()

    if src:
        prefix = " ".join(f"{short} {src}".split())          # collapse double spaces
        name = " ".join(f"{prefix} Connection".split())
        description = " ".join(
            f"Integration connection for {prefix} source system".split()
        )
        return name, description

    # No source system → fall back to the API/touchpoint name for both
    return fallback_name, fallback_name


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


def _get_source_system(tech, func):
    """Resolve the source system for a touchpoint.
    Prefers the technical record, falls back to the functional record.
    """
    if tech and (getattr(tech, "source_system", "") or "").strip():
        return tech.source_system.strip()
    if func and (getattr(func, "source_system", "") or "").strip():
        return func.source_system.strip()
    return ""


def _resolve_connection_for_source(db, current_tp_id, source_system, uat_url, prod_url):
    """Group connections by Source System.

    CRM model: one connection per source system (same base URL), many EDS
    (one per method) under it. This scans sibling touchpoints sharing the
    same source system and:
      - validates their base URLs match (a source system must map to ONE URL)
      - returns an existing connection id to reuse if one was already created

    Returns: (shared_connection_id_or_None, error_message_or_None)
    """
    if not source_system:
        # No source system => cannot group; treat as standalone (no reuse, no validation)
        return None, None

    src_lower = source_system.lower()
    shared_cid = None

    siblings = db.query(IDRTechnical).filter(
        IDRTechnical.touchpoint_id != current_tp_id
    ).all()

    for other in siblings:
        if (getattr(other, "source_system", "") or "").strip().lower() != src_lower:
            continue

        td = other.technical_details if isinstance(other.technical_details, dict) else {}
        other_uat = (td.get("uatUrl") or "").strip()
        other_prod = (td.get("prodUrl") or "").strip()

        # Validate URL consistency (only compare when both sides have a value)
        if other_uat and uat_url and other_uat.lower() != uat_url.lower():
            return None, (
                f"Source system '{source_system}' already has a connection using UAT URL "
                f"'{other_uat}', but this touchpoint has '{uat_url}'. A source system can map "
                f"to only one URL. To resolve, either:\n"
                f"1. Change this touchpoint's UAT URL to '{other_uat}' — it will then use the "
                f"existing connection; or\n"
                f"2. Change the source system name — a new connection will be created for it."
            )
        if other_prod and prod_url and other_prod.lower() != prod_url.lower():
            return None, (
                f"Source system '{source_system}' already has a connection using Prod URL "
                f"'{other_prod}', but this touchpoint has '{prod_url}'. A source system can map "
                f"to only one URL. To resolve, either:\n"
                f"1. Change this touchpoint's Prod URL to '{other_prod}' — it will then use the "
                f"existing connection; or\n"
                f"2. Change the source system name — a new connection will be created for it."
            )

        # Same source system + consistent URL => reuse its connection if present
        if shared_cid is None and td.get("crmConnectionId") is not None:
            try:
                shared_cid = int(td["crmConnectionId"])
            except (ValueError, TypeError):
                pass

    return shared_cid, None


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


def _fetch_connection_details(cursor, schema, db_type, owner_id, connection_id):
    """Fetch NAME + DESCRIPTION for an existing connection straight from CRM DB.

    Used to DISPLAY an already-created connection (we never modify it).
    Returns (name, description) or (None, None) if the row isn't found.
    """
    sql = (f"SELECT NAME, DESCRIPTION FROM {schema}.MASHUPCONNECTION "
           f"WHERE OWNERID = :owner AND CONNECTIONID = :cid")
    sql, params = adapt_query(sql, {"owner": owner_id, "cid": connection_id}, db_type)
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if not row:
        return None, None
    name = row[0] if row[0] is not None else ""
    desc = row[1] if row[1] is not None else ""
    return name, desc


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


def _build_preview_dict(owner_id, connection_id, conn_name, conn_description, is_update, db_type=DB_TYPE_ORACLE):
    now = now_sql(db_type)
    return {
        "OWNERID": owner_id,
        "CONNECTIONID": connection_id,
        "NAME": conn_name,
        "DESCRIPTION": conn_description,
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

def _do_insert(cursor, schema, db_type, owner_id, connection_id, conn_name, conn_description):
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
        "name": conn_name, "description": conn_description,
        "type": 10, "timeout": 0, "isenabled": 1,
        "createdby": "1", "lastmodifiedby": "1",
        "isfreshconnection": 0, "encryptiontype": -1,
        "useencryption": 0, "keysize": -1,
    }
    sql, params = adapt_query(sql, params, db_type)
    cursor.execute(sql, params)


def _do_connection_update(cursor, schema, db_type, owner_id, connection_id, conn_name, conn_description):
    """UPDATE an existing MASHUPCONNECTION in place.

    Never deletes — a delete would violate FK_MashupDataSource_MashupConnection
    when a datasource already references this connection. Only the fields that
    can change on re-push are updated.
    """
    now = now_sql(db_type)
    sql = (f"UPDATE {schema}.MASHUPCONNECTION "
           f"SET NAME = :name, DESCRIPTION = :description, LASTMODIFIEDON = {now} "
           f"WHERE OWNERID = :owner AND CONNECTIONID = :cid")
    params = {
        "name": conn_name, "description": conn_description,
        "owner": owner_id, "cid": connection_id,
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


def _do_ws_update(cursor, schema, db_type, owner_id, connection_id,
                  service_name, service_xml, request_header_key_xml):
    """UPDATE an existing MASHUPWSCONNECTION in place (no delete).

    Only the fields that change on re-push are updated:
    SERVICENAME, SERVICEXML, REQUESTHEADERKEYXML.
    """
    sql = (f"UPDATE {schema}.MASHUPWSCONNECTION "
           f"SET SERVICENAME = :servicename, "
           f"SERVICEXML = :servicexml, "
           f"REQUESTHEADERKEYXML = :requestheaderkeyxml "
           f"WHERE OWNERID = :owner AND CONNECTIONID = :cid")
    params = {
        "servicename": service_name,
        "servicexml": service_xml,
        "requestheaderkeyxml": request_header_key_xml,
        "owner": owner_id, "cid": connection_id,
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
    db_type, crm_config, schema, owner_id, project_short = _get_crm_context(tp, db)

    api_name = _get_api_name(tech, tp)
    if not api_name:
        raise HTTPException(status_code=400, detail="API Name is empty.")

    # Connection is named after the source system
    source_system = _get_source_system(tech, func)
    conn_name, conn_description = _build_connection_naming(project_short, source_system, api_name)

    td = tech.technical_details if (tech and isinstance(tech.technical_details, dict)) else {}
    uat_url = (td.get("uatUrl") or "").strip()
    prod_url = (td.get("prodUrl") or "").strip()

    stored_cid = _get_stored_connection_id(tech)

    # Surface URL-consistency conflicts early, and find a shared connection if any
    shared_cid = None
    if not stored_cid:
        shared_cid, conflict = _resolve_connection_for_source(
            db, tp_id, source_system, uat_url, prod_url
        )
        if conflict:
            raise HTTPException(status_code=400, detail=conflict)

    if stored_cid:
        conn = None
        try:
            conn = get_crm_connection(db_type, crm_config)
            cursor = conn.cursor()
            if _verify_connection_exists(cursor, schema, db_type, owner_id, stored_cid):
                # Existing connection — display the ACTUAL values from CRM DB.
                fetched_name, fetched_desc = _fetch_connection_details(
                    cursor, schema, db_type, owner_id, stored_cid
                )
                disp_name = fetched_name or conn_name
                disp_desc = fetched_desc if fetched_desc is not None else conn_description
                return {
                    "tp_id": tp_id, "tp_name": tp.name,
                    "api_name": disp_name, "source_system": source_system,
                    "is_update": True, "existing": True,
                    "preview": _build_preview_dict(owner_id, stored_cid, disp_name, disp_desc, True, db_type),
                }
        except HTTPException:
            raise
        except Exception:
            return {
                "tp_id": tp_id, "tp_name": tp.name,
                "api_name": conn_name, "source_system": source_system,
                "is_update": True, "existing": True,
                "preview": _build_preview_dict(owner_id, stored_cid, conn_name, conn_description, True, db_type),
            }
        finally:
            if conn:
                conn.close()

    # If a connection for this source system already exists, fetch + display it
    if shared_cid:
        conn = None
        try:
            conn = get_crm_connection(db_type, crm_config)
            cursor = conn.cursor()
            fetched_name, fetched_desc = _fetch_connection_details(
                cursor, schema, db_type, owner_id, shared_cid
            )
            disp_name = fetched_name or conn_name
            disp_desc = fetched_desc if fetched_desc is not None else conn_description
        except Exception:
            disp_name, disp_desc = conn_name, conn_description
        finally:
            if conn:
                conn.close()
        return {
            "tp_id": tp_id, "tp_name": tp.name,
            "api_name": disp_name, "source_system": source_system,
            "is_update": True, "existing": True, "shared": True,
            "preview": _build_preview_dict(owner_id, shared_cid, disp_name, disp_desc, True, db_type),
        }

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
            "api_name": conn_name, "source_system": source_system,
            "is_update": False,
            "preview": _build_preview_dict(owner_id, connection_id, conn_name, conn_description, False, db_type),
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
    db_type, crm_config, schema, owner_id, project_short = _get_crm_context(tp, db)

    api_name = _get_api_name(tech, tp)
    if not api_name:
        raise HTTPException(status_code=400, detail="API Name is empty.")

    # Connection is named after the SOURCE SYSTEM (one connection per source system).
    source_system = _get_source_system(tech, func)
    conn_name, conn_description = _build_connection_naming(project_short, source_system, api_name)   # fall back to API name if no source system

    td = tech.technical_details if (tech and isinstance(tech.technical_details, dict)) else {}
    uat_url = (td.get("uatUrl") or "").strip()
    prod_url = (td.get("prodUrl") or "").strip()

    stored_cid = _get_stored_connection_id(tech)

    # Group by source system + validate URL consistency
    shared_cid = None
    if not stored_cid:
        shared_cid, conflict = _resolve_connection_for_source(
            db, tp_id, source_system, uat_url, prod_url
        )
        if conflict:
            raise HTTPException(status_code=400, detail=conflict)

    conn = None
    try:
        conn = get_crm_connection(db_type, crm_config)
        cursor = conn.cursor()

        candidate_cid = stored_cid or shared_cid

        if candidate_cid and _verify_connection_exists(cursor, schema, db_type, owner_id, candidate_cid):
            # Connection already exists in CRM — DO NOT modify it.
            # Fetch its details and link this touchpoint to it.
            connection_id = candidate_cid
            existing = True
            fetched_name, fetched_desc = _fetch_connection_details(
                cursor, schema, db_type, owner_id, connection_id
            )
            conn_name = fetched_name or conn_name
            conn_description = fetched_desc if fetched_desc is not None else conn_description

        elif candidate_cid:
            # We have a stored/shared ID but the row is missing in CRM — create with that ID.
            connection_id = candidate_cid
            existing = False
            _do_insert(cursor, schema, db_type, owner_id, connection_id, conn_name, conn_description)

        else:
            # Brand new connection — allocate the next ID and create.
            existing = False
            connection_id = atomic_increment(cursor, schema, db_type, owner_id, ITEM_ID)
            _do_insert(cursor, schema, db_type, owner_id, connection_id, conn_name, conn_description)

        conn.commit()
        _save_connection_id(db, tech, connection_id)

        action = "linked (existing)" if existing else "created"
        reused = " (shared by source system)" if (shared_cid and not stored_cid) else ""
        db.add(IDRActionLog(
            touchpoint_id=tp_id, action_type="Manual Update", action_by="User",
            comment=f"CRM MASHUPCONNECTION {action}. CONNECTIONID={connection_id}, NAME={conn_name}{reused}",
        ))
        db.commit()

        return {
            "success": True, "connection_id": connection_id,
            "name": conn_name, "description": conn_description,
            "source_system": source_system,
            "existing": existing,
            "is_update": existing,   # kept for frontend compatibility
            "shared": bool(shared_cid and not stored_cid),
            "message": (
                f"Connection already exists in CRM (ID {connection_id}); "
                f"details fetched and linked — not modified."
                if existing else
                f"MASHUPCONNECTION created successfully for source system "
                f"'{conn_name}'. CONNECTIONID = {connection_id}"
                + (" (reused existing connection for this source system)"
                   if (shared_cid and not stored_cid) else "")
            ),
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
    db_type, crm_config, schema, owner_id, project_short = _get_crm_context(tp, db)

    stored_cid = _get_stored_connection_id(tech)
    if not stored_cid:
        raise HTTPException(status_code=400, detail='Push MASHUPCONNECTION first.')

    api_name = _get_api_name(tech, tp)
    if not api_name:
        raise HTTPException(status_code=400, detail="API Name is empty.")

    # WS service name mirrors the connection name (source system)
    source_system = _get_source_system(tech, func)
    conn_name, conn_description = _build_connection_naming(project_short, source_system, api_name)

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
            "SERVICENAME": conn_name, "SERVICELOCATION": service_location,
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
    db_type, crm_config, schema, owner_id, project_short = _get_crm_context(tp, db)

    stored_cid = _get_stored_connection_id(tech)
    if not stored_cid:
        raise HTTPException(status_code=400, detail='Push MASHUPCONNECTION first.')

    api_name = _get_api_name(tech, tp)
    if not api_name:
        raise HTTPException(status_code=400, detail="API Name is empty.")

    # WS service name mirrors the connection name (source system)
    source_system = _get_source_system(tech, func)
    conn_name, conn_description = _build_connection_naming(project_short, source_system, api_name)

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

        existing = _ws_row_exists(cursor, schema, db_type, owner_id, stored_cid)
        if existing:
            # WS connection already exists — DO NOT modify it.
            pass
        else:
            _do_ws_insert(cursor, schema, db_type, owner_id, stored_cid, conn_name,
                          service_location, service_xml, request_header_key_xml)
        conn.commit()

        action = "linked (existing)" if existing else "created"
        db.add(IDRActionLog(
            touchpoint_id=tp_id, action_type="Manual Update", action_by="User",
            comment=f"CRM MASHUPWSCONNECTION {action}. CONNECTIONID={stored_cid}",
        ))
        db.commit()

        return {
            "success": True, "connection_id": stored_cid,
            "existing": existing, "is_update": existing,
            "message": (
                f"WS connection already exists in CRM (CONNECTIONID = {stored_cid}); not modified."
                if existing else
                f"MASHUPWSCONNECTION created successfully. CONNECTIONID = {stored_cid}"
            ),
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

@router.get("/api/crm/datasource/check/{tp_id}")
def crm_datasource_check(tp_id: int, db: Session = Depends(get_db)):
    """Lightweight check used by the UI to decide whether to show an
    'update existing datasource?' confirmation popup. Does NOT modify the CRM DB.

    Returns: { is_update, datasource_id, datasource_name }
    """
    tp, tech, func = _get_tp_data(tp_id, db)
    db_type, crm_config, schema, owner_id, project_short = _get_crm_context(tp, db)

    stored_dsid = _get_stored_datasource_id(tech)
    if not stored_dsid:
        return {"is_update": False, "datasource_id": None, "datasource_name": None}

    conn = None
    try:
        conn = get_crm_connection(db_type, crm_config)
        cursor = conn.cursor()
        sql = (f"SELECT NAME FROM {schema}.MASHUPDATASOURCE "
               f"WHERE OWNERID = :owner AND DATASOURCEID = :dsid")
        sql, params = adapt_query(sql, {"owner": owner_id, "dsid": stored_dsid}, db_type)
        cursor.execute(sql, params)
        row = cursor.fetchone()
        if row:
            return {"is_update": True, "datasource_id": stored_dsid, "datasource_name": row[0]}
        return {"is_update": False, "datasource_id": None, "datasource_name": None}
    except Exception:
        # If we can't verify, err on the side of confirming (treat as update)
        return {"is_update": True, "datasource_id": stored_dsid, "datasource_name": None}
    finally:
        if conn:
            conn.close()


@router.post("/api/crm/datasource/insert/{tp_id}")
def crm_datasource_insert(
    tp_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    tp, tech, func = _get_tp_data(tp_id, db)
    db_type, crm_config, schema, owner_id, project_short = _get_crm_context(tp, db)

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