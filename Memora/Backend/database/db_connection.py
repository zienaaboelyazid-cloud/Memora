"""
Single shared place that opens MySQL connections for every database/*.py
module (FaceDatabase, PatientMemory, PatientProfile, SafeZoneStore,
CaregiverAuth). Nothing else in the codebase should call
mysql.connector.connect(...) directly - always go through get_connection()
here, so the credentials only live in one place (config.py).
"""

import mysql.connector

from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE

_database_ready = False


def _ensure_database_exists():
    """
    Runs once per process: connects WITHOUT selecting a database and
    creates it if it doesn't exist yet, so you don't have to manually
    run "CREATE DATABASE memora;" yourself before first launch.
    """
    global _database_ready
    if _database_ready:
        return

    conn = mysql.connector.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD,
    )
    try:
        cur = conn.cursor()
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()

    _database_ready = True


def get_connection():
    """
    Returns a fresh MySQL connection, already pointed at MYSQL_DATABASE.
    Every database/*.py class calls this instead of managing its own
    connection logic - same pattern as the old sqlite3.connect(db_path).
    """
    _ensure_database_exists()
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )
