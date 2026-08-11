import os
import sqlite3
import threading
from datetime import datetime, timedelta

import mysql.connector

DB_FILE = os.path.join(os.path.dirname(__file__), ".canpack_data.db")

MYSQL_HOST = os.getenv("MYSQL_HOST", "canpack-elynizar-dd70.h.aivencloud.com")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "10132"))
MYSQL_USER = os.getenv("MYSQL_USER", "avnadmin")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "AVNS_AVtS75AXF4DJYreklu-")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "defaultdb")
MYSQL_SSL_MODE = os.getenv("MYSQL_SSL_MODE", "REQUIRED")

# In-process lock to serialize write operations and avoid SQLITE_BUSY
_WRITE_LOCK = threading.Lock()


def get_connection(timeout: float = 30.0):
    """Return a new sqlite3 connection configured for writes.

    Uses WAL mode and a busy timeout, then returns a writable connection.
    """
    conn = sqlite3.connect(DB_FILE, timeout=timeout, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    except Exception:
        pass
    return conn


def get_read_connection(timeout: float = 60.0):
    """Return a new sqlite3 read-only connection for concurrent Streamlit reads."""
    uri = f"file:{DB_FILE}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=timeout, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 10000")
    except Exception:
        pass
    return conn


def execute_write(sql: str, params: tuple = ()):  # helper to serialize writes
    """Execute a write SQL statement using a short lock to avoid SQLITE_BUSY.

    Returns the sqlite3.Cursor for the executed statement.
    """
    with _WRITE_LOCK:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur
        finally:
            conn.close()


def init_db(seed_demo_data=True):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            armoire TEXT NOT NULL,
            courant_mA REAL NOT NULL,
            moyenne REAL NOT NULL,
            statut TEXT NOT NULL,
            horodatage TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS alertes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            horodatage TEXT NOT NULL,
            armoire TEXT NOT NULL,
            niveau TEXT NOT NULL,
            valeur_mA REAL NOT NULL
        )
        """
    )
    cursor.execute(
        """
        DELETE FROM alertes
        WHERE rowid NOT IN (
            SELECT MIN(rowid)
            FROM alertes
            GROUP BY armoire, horodatage, niveau, valeur_mA
        )
        """
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_alertes_unique ON alertes (armoire, horodatage, niveau, valeur_mA)"
    )
    conn.commit()

    if seed_demo_data:
        _seed_sample_data(conn)

    return conn


def get_mysql_connection(timeout: int = 5):
    """Return a connected MySQL connection or None if unavailable."""
    if not MYSQL_HOST or not MYSQL_USER or not MYSQL_DATABASE:
        return None

    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            connection_timeout=timeout,
            ssl_mode=MYSQL_SSL_MODE,
        )
        return conn
    except mysql.connector.Error:
        return None


def get_mysql_source():
    """Return the configured MySQL host if reachable, else None."""
    if get_mysql_connection() is not None:
        return MYSQL_HOST
    return None


def _seed_sample_data(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM mesures")
    count = cursor.fetchone()[0]
    if count > 0:
        return

    now = datetime.utcnow()
    armoires = [
        ("Body Maker", 18.5, 15.0, "normal"),
        ("Zone Laveuse", 23.7, 20.0, "PRECOCE"),
        ("LSM (Vernissage)", 32.1, 28.0, "CRITIQUE"),
    ]
    for nom, courant, moyenne, statut in armoires:
        for minutes_ago in range(120, -1, -12):
            ts = (now - timedelta(minutes=minutes_ago)).isoformat()
            value = max(0.0, courant + (minutes_ago - 60) * 0.05)
            avg = max(0.0, moyenne + (minutes_ago - 60) * 0.03)
            status = statut if minutes_ago < 24 else "normal"
            cursor.execute(
                "INSERT INTO mesures (armoire, courant_mA, moyenne, statut, horodatage) VALUES (?, ?, ?, ?, ?)",
                (nom, value, avg, status, ts),
            )

    alertes = [
        (now - timedelta(hours=1), "Zone Laveuse", "PRECOCE", 23.7),
        (now - timedelta(hours=2), "LSM (Vernissage)", "CRITIQUE", 32.1),
    ]
    for ts, nom, niveau, valeur in alertes:
        cursor.execute(
            "INSERT INTO alertes (horodatage, armoire, niveau, valeur_mA) VALUES (?, ?, ?, ?)",
            (ts.isoformat(), nom, niveau, valeur),
        )

    conn.commit()