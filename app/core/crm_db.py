"""
Multi-DB CRM connection factory.

Supports Oracle (oracledb), SQL Server (pyodbc), PostgreSQL (psycopg2).
Per-project CRM credentials are stored in Project.crm_db_config (JSON).

Backward compatibility: if a project has no crm_db_config, falls back to
ORACLE_* env vars so existing Oracle-only deployments are unaffected.
"""

import os
import re

DB_TYPE_ORACLE = "oracle"
DB_TYPE_SQLSERVER = "sqlserver"
DB_TYPE_POSTGRES = "postgres"

# Oracle thick mode is initialized lazily, exactly once per process.
# Required because the CRMNext Oracle DB uses national character set id 871
# for NCLOB columns (XSLT etc.), which thin mode does not support (DPY-3012).
_ORACLE_THICK_INITIALIZED = False


def _ensure_oracle_thick_mode():
    """Initialize python-oracledb thick mode once. Safe to call repeatedly.

    Must run before the first Oracle connection. SQL Server / PostgreSQL
    deployments never call this, so they don't need the Instant Client.
    """
    global _ORACLE_THICK_INITIALIZED
    if _ORACLE_THICK_INITIALIZED:
        return
    try:
        import oracledb
        instant_client_dir = os.environ.get(
            "ORACLE_INSTANT_CLIENT",
            r"C:\Users\GautamHawdiya\Downloads\instantclient-basic-windows.x64-23.26.2.0.0\instantclient_23_0",
        )
        oracledb.init_oracle_client(lib_dir=instant_client_dir)
        print(f"[crm_db] Oracle thick mode initialized ({instant_client_dir}).")
    except Exception as e:
        # Already initialized (module reload) or path issue — don't retry forever.
        print(f"[crm_db] Oracle thick mode init note: {e}")
    finally:
        _ORACLE_THICK_INITIALIZED = True


# ---------------------------------------------------------------------------
# PROJECT CONFIG RESOLUTION
# ---------------------------------------------------------------------------

def get_crm_config_for_project(project) -> tuple:
    """Return (db_type, config_dict) for a project.

    Falls back to .env Oracle credentials when:
      - crm_db_type is 'oracle' (or unset)
      - crm_db_config has no 'host' key (i.e. never explicitly configured)
    This keeps all existing Oracle projects working without any data migration.
    """
    db_type = (getattr(project, "crm_db_type", None) or DB_TYPE_ORACLE).lower().strip()
    config = dict(getattr(project, "crm_db_config", None) or {})

    if db_type == DB_TYPE_ORACLE and not config.get("host"):
        # Legacy path: pull from environment (existing deployments)
        config = {
            "host":     os.environ.get("ORACLE_HOST", ""),
            "port":     int(os.environ.get("ORACLE_PORT", "1521")),
            "service":  os.environ.get("ORACLE_SERVICE", ""),
            "user":     os.environ.get("ORACLE_USER", "").strip(),
            "password": os.environ.get("ORACLE_PASSWORD", ""),
            "schema":   os.environ.get("ORACLE_SCHEMA", "").strip(),
        }

    return db_type, config


# ---------------------------------------------------------------------------
# CONNECTION FACTORY
# ---------------------------------------------------------------------------

def get_crm_connection(db_type: str, config: dict):
    """Return an open DB-API 2.0 connection for the given db_type + config.
    Caller is responsible for closing the connection.
    """
    if db_type == DB_TYPE_ORACLE:
        return _connect_oracle(config)
    elif db_type == DB_TYPE_SQLSERVER:
        return _connect_sqlserver(config)
    elif db_type == DB_TYPE_POSTGRES:
        return _connect_postgres(config)
    else:
        raise RuntimeError(
            f"Unknown CRM DB type: '{db_type}'. "
            f"Valid values: oracle, sqlserver, postgres."
        )


def get_owner_id(config: dict) -> int:
    """Return the CRM OWNERID from the project config.

    Each bank/deployment uses a different OWNERID in the CRM Mashup tables.
    Falls back to 914 (legacy default) for existing Oracle projects that
    haven't set owner_id in their config.
    """
    oid = config.get("owner_id")
    if oid is not None:
        try:
            return int(oid)
        except (ValueError, TypeError):
            pass
    return 914  # legacy default


def get_project_short_name(config: dict) -> str:
    """Return the project short name (e.g. 'SBI', 'PNB') from the project config.

    Used to name CRM connections. Set it per project in crm_db_config as
    "project_short_name". Returns "" if not configured (caller falls back
    to the full project name).
    """
    return (config.get("project_short_name") or "").strip()


def get_crm_schema(db_type: str, config: dict) -> str:
    """Return the schema prefix for use in SQL (e.g. 'dbo', 'public', 'MY_SCHEMA').

    Defaults per DB type when not explicitly set.
    For Oracle, we default to the 'user' because our SQL strings use 
    f"{schema}.TABLENAME". If schema is empty, it results in ".TABLENAME" 
    which causes ORA-00903.
    """
    schema = (config.get("schema") or "").strip()
    if schema:
        return schema
        
    # If the user left 'schema' blank in the UI, provide the safe default
    if db_type == DB_TYPE_ORACLE:
        return (config.get("user") or "").strip()
    elif db_type == DB_TYPE_SQLSERVER:
        return "dbo"
    elif db_type == DB_TYPE_POSTGRES:
        return "public"
        
    return "dbo"

# ---------------------------------------------------------------------------
# DIALECT HELPERS — used by crm.py
# ---------------------------------------------------------------------------

def now_sql(db_type: str) -> str:
    """SQL expression for current timestamp, dialect-specific.

    Embedded directly in SQL strings as an f-string interpolation,
    NOT as a bind parameter (it's a function call, not a value).
    """
    return {
        DB_TYPE_ORACLE:    "SYSDATE",
        DB_TYPE_SQLSERVER: "GETDATE()",
        DB_TYPE_POSTGRES:  "NOW()",
    }.get(db_type, "NOW()")


def adapt_query(sql: str, params: dict, db_type: str):
    """Convert Oracle-style ':name' params to the target DB's format.

    Oracle     → ':name'  with dict        (oracledb  – unchanged)
    SQL Server → '?'      with ordered list (pyodbc   – positional)
    PostgreSQL → '%(n)s'  with dict        (psycopg2  – named)

    Returns: (adapted_sql, adapted_params)

    Note: SQL function calls embedded via f-string (SYSDATE / GETDATE() / NOW())
    are plain text in the SQL string and are NOT affected by this conversion.
    """
    if db_type == DB_TYPE_ORACLE:
        return sql, params

    if db_type == DB_TYPE_SQLSERVER:
        # Extract param names in appearance order, replace each with '?'
        order = re.findall(r":([A-Za-z_]\w*)", sql)
        adapted = re.sub(r":[A-Za-z_]\w*", "?", sql)
        return adapted, [params[k] for k in order]

    # PostgreSQL: ':name' → '%(name)s'
    adapted = re.sub(r":([A-Za-z_]\w*)", r"%(\1)s", sql)
    return adapted, params


def atomic_increment(cursor, schema: str, db_type: str, owner_id: int, item_id: int) -> int:
    """Atomically increment MASHUPIDLIST.LASTID and return the new value.

    This is the only operation that is truly DB-API incompatible across
    the three engines — each has its own pattern for UPDATE + return value:

      Oracle     → RETURNING … INTO cursor.var()
      SQL Server → OUTPUT INSERTED.column
      PostgreSQL → RETURNING column
    """
    if db_type == DB_TYPE_ORACLE:
        import oracledb
        new_id_var = cursor.var(oracledb.NUMBER)
        cursor.execute(
            f"UPDATE {schema}.MASHUPIDLIST SET LASTID = LASTID + 1 "
            f"WHERE OWNERID = :owner AND ITEMID = :item "
            f"RETURNING LASTID INTO :new_id",
            {"owner": owner_id, "item": item_id, "new_id": new_id_var},
        )
        return int(new_id_var.getvalue()[0])

    elif db_type == DB_TYPE_SQLSERVER:
        # OUTPUT clause returns the updated row as a result set
        cursor.execute(
            f"UPDATE {schema}.MASHUPIDLIST SET LASTID = LASTID + 1 "
            f"OUTPUT INSERTED.LASTID "
            f"WHERE OWNERID = ? AND ITEMID = ?",
            (owner_id, item_id),
        )
        return int(cursor.fetchone()[0])

    else:  # postgres
        cursor.execute(
            f"UPDATE {schema}.MASHUPIDLIST SET LASTID = LASTID + 1 "
            f"WHERE OWNERID = %(owner)s AND ITEMID = %(item)s "
            f"RETURNING LASTID",
            {"owner": owner_id, "item": item_id},
        )
        return int(cursor.fetchone()[0])


# ---------------------------------------------------------------------------
# PRIVATE CONNECT FUNCTIONS
# ---------------------------------------------------------------------------

def _connect_oracle(config: dict):
    try:
        import oracledb
    except ImportError:
        raise RuntimeError("oracledb not installed. Run: pip install oracledb")

    # Thick mode required for NCLOB columns (charset 871) — must run before connect
    _ensure_oracle_thick_mode()

    host     = config.get("host", "")
    port     = int(config.get("port", 1521))
    service  = config.get("service", "")
    user     = config.get("user", "").strip()
    password = config.get("password", "")

    if not all([host, service, user, password]):
        raise RuntimeError(
            "Oracle credentials incomplete. "
            "Set host/service/user/password in the project's CRM config."
        )
    try:
        return oracledb.connect(user=user, password=password, dsn=f"{host}:{port}/{service}")
    except Exception as e:
        raise RuntimeError(f"Oracle connection failed: {e}")


def _connect_sqlserver(config: dict):
    try:
        import pyodbc
    except ImportError:
        raise RuntimeError(
            "pyodbc not installed. Run: pip install pyodbc\n"
            "Also install 'ODBC Driver 17 for SQL Server' from Microsoft."
        )

    host     = config.get("host", "")
    port     = int(config.get("port", 1433))
    database = config.get("database", "")
    user     = config.get("user", "").strip()
    password = config.get("password", "")
    driver   = config.get("driver", "ODBC Driver 17 for SQL Server")

    if not all([host, database, user, password]):
        raise RuntimeError(
            "SQL Server credentials incomplete. "
            "Set host/database/user/password in the project's CRM config."
        )

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={host},{port};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
    )
    try:
        conn = pyodbc.connect(conn_str)
        conn.autocommit = False
        return conn
    except Exception as e:
        raise RuntimeError(f"SQL Server connection failed: {e}")


def _connect_postgres(config: dict):
    try:
        import psycopg2
    except ImportError:
        raise RuntimeError("psycopg2 not installed. Run: pip install psycopg2-binary")

    host     = config.get("host", "")
    port     = int(config.get("port", 5432))
    database = config.get("database", "")
    user     = config.get("user", "").strip()
    password = config.get("password", "")

    if not all([host, database, user, password]):
        raise RuntimeError(
            "PostgreSQL credentials incomplete. "
            "Set host/database/user/password in the project's CRM config."
        )
    try:
        return psycopg2.connect(
            host=host, port=port, dbname=database, user=user, password=password
        )
    except Exception as e:
        raise RuntimeError(f"PostgreSQL connection failed: {e}")