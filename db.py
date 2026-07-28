import os
import sqlite3
from datetime import datetime, timedelta

DB_FILE = os.path.join(os.path.dirname(__file__), ".canpack_data.db")


def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


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
