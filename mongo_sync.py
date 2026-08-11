import os
import sqlite3
from datetime import datetime

import mysql.connector

DB_FILE = os.path.join(os.path.dirname(__file__), ".canpack_data.db")
MYSQL_HOST = os.getenv("MYSQL_HOST", "canpack-elynizar-dd70.h.aivencloud.com")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "10132"))
MYSQL_USER = os.getenv("MYSQL_USER", "avnadmin")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "AVNS_AVtS75AXF4DJYreklu-")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "defaultdb")
MYSQL_SSL_MODE = os.getenv("MYSQL_SSL_MODE", "REQUIRED")


def get_sqlite_connection():
    return sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)


def get_mysql_connection():
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        autocommit=False,
    )


def ensure_mysql_schema(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            cabinet VARCHAR(50),
            courant_mA FLOAT,
            moyenne FLOAT,
            statut VARCHAR(20),
            horodatage DATETIME,
            INDEX idx_cabinet_time (cabinet, horodatage),
            UNIQUE KEY ux_readings_unique (cabinet, horodatage, courant_mA, moyenne, statut)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            cabinet VARCHAR(50),
            niveau VARCHAR(20),
            valeur_mA FLOAT,
            horodatage DATETIME,
            INDEX idx_cabinet_time (cabinet, horodatage),
            UNIQUE KEY ux_alerts_unique (cabinet, horodatage, niveau, valeur_mA)
        )
        """
    )
    conn.commit()


def sync_table(sqlite_conn, mysql_conn, sqlite_table, mysql_table, sqlite_columns, mysql_columns, where_clause="", params=()):
    sqlite_cursor = sqlite_conn.cursor()
    mysql_cursor = mysql_conn.cursor()

    mysql_cursor.execute(f"SELECT MAX(horodatage) FROM {mysql_table}")
    last_remote = mysql_cursor.fetchone()[0]

    query = f"SELECT {', '.join(sqlite_columns)} FROM {sqlite_table}"
    if last_remote is not None:
        last_remote_str = last_remote.isoformat() if hasattr(last_remote, "isoformat") else str(last_remote)
        query += " WHERE horodatage > ?"
        params = params + (last_remote_str,)
    query += " ORDER BY horodatage ASC"

    sqlite_cursor.execute(query, params)
    rows = sqlite_cursor.fetchall()
    if not rows:
        print(f"{mysql_table}: aucune donnée nouvelle à synchroniser")
        return

    placeholders = ", ".join(["%s"] * len(mysql_columns))
    insert_sql = f"INSERT IGNORE INTO {mysql_table} ({', '.join(mysql_columns)}) VALUES ({placeholders})"
    mysql_cursor.executemany(insert_sql, rows)
    mysql_conn.commit()
    print(f"{mysql_table}: synchronisé {len(rows)} lignes")


def main():
    if not os.path.exists(DB_FILE):
        print(f"Fichier SQLite introuvable: {DB_FILE}")
        return

    sqlite_conn = get_sqlite_connection()
    mysql_conn = get_mysql_connection()
    try:
        ensure_mysql_schema(mysql_conn)
        sync_table(
            sqlite_conn,
            mysql_conn,
            "mesures",
            "readings",
            ["armoire", "courant_mA", "moyenne", "statut", "horodatage"],
            ["cabinet", "courant_mA", "moyenne", "statut", "horodatage"],
        )
        sync_table(
            sqlite_conn,
            mysql_conn,
            "alertes",
            "alerts",
            ["horodatage", "armoire", "niveau", "valeur_mA"],
            ["horodatage", "cabinet", "niveau", "valeur_mA"],
        )
    except mysql.connector.Error as err:
        print(f"Erreur MySQL: {err}")
    finally:
        sqlite_conn.close()
        mysql_conn.close()


if __name__ == "__main__":
    main()
