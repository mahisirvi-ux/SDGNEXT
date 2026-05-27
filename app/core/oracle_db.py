"""Oracle DB connection for CRMNext integration.

Uses the oracledb thin driver (no Oracle Client install needed).
Credentials loaded from .env via python-dotenv.
"""

import os
import oracledb


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