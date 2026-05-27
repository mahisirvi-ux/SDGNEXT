"""Oracle DB connection for CRMNext integration.

Uses oracledb in THICK mode (Oracle Instant Client required) to support
the national character set (NCLOB columns) used by the CRMNext schema.
Credentials loaded from .env via python-dotenv.
"""

import os
import oracledb

# Initialize thick mode once at module load.
# Thick mode is required because the CRMNext Oracle DB uses national
# character set id 871 for NCLOB columns (XSLT etc.) which is not
# supported by python-oracledb thin mode (DPY-3012).
_INSTANT_CLIENT_DIR = os.environ.get(
    "ORACLE_INSTANT_CLIENT",
    r"D:\oracle_instantclient\instantclient_23_4"
)

try:
    oracledb.init_oracle_client(lib_dir=_INSTANT_CLIENT_DIR)
except Exception as e:
    # Already initialized (e.g. module reloaded) or path issue
    print(f"[oracle_db] init_oracle_client note: {e}")


def get_oracle_connection():
    """Return an open oracledb connection to CRMNext Oracle DB.

    Caller is responsible for closing the connection.
    Raises RuntimeError if credentials are missing or connection fails.
    """
    host = os.environ.get("ORACLE_HOST", "")
    port = int(os.environ.get("ORACLE_PORT", "1521"))
    service = os.environ.get("ORACLE_SERVICE", "")
    user = os.environ.get("ORACLE_USER", "").strip()
    password = os.environ.get("ORACLE_PASSWORD", "")

    if not all([host, service, user, password]):
        raise RuntimeError(
            "Oracle credentials missing. Check .env for ORACLE_HOST, "
            "ORACLE_PORT, ORACLE_SERVICE, ORACLE_USER, ORACLE_PASSWORD."
        )

    dsn = f"{host}:{port}/{service}"

    try:
        conn = oracledb.connect(user=user, password=password, dsn=dsn)
        return conn
    except Exception as e:
        raise RuntimeError(f"Oracle connection failed: {e}")


def get_oracle_schema():
    """Return the Oracle schema prefix (e.g. SIB_DEV_BUSINESSNEXT_AUG25)."""
    return os.environ.get("ORACLE_SCHEMA", "SIB_DEV_BUSINESSNEXT_AUG25").strip()