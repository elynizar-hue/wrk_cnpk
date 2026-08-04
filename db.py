import os
import sqlite3
import threading
from datetime import datetime, timedelta

DB_FILE = os.path.join(os.path.dirname(__file__), ".canpack_data.db")

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
    conn.commit()

    if seed_demo_data:
        _seed_sample_data(conn)

    return conn


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