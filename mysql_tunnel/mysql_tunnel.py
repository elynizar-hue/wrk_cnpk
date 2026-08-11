import os
import socket
import threading
import mysql.connector
from mysql.connector import CMySQLConnection

MYSQL_HOST = os.getenv("MYSQL_HOST", "canpack-elynizar-dd70.h.aivencloud.com")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "10132"))
MYSQL_USER = os.getenv("MYSQL_USER", "avnadmin")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "AVNS_AVtS75AXF4DJYreklu-")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "defaultdb")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "3306"))
LISTEN_HOST = os.getenv("LISTEN_HOST", "127.0.0.1")


def get_mysql_connection():
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        ssl_disabled=False,
    )


def handle_client(client_sock: socket.socket, mysql_conn: CMySQLConnection):
    try:
        mysql_sock = mysql_conn.socket
        client_sock.sendall(b"")

        def forward(source: socket.socket, target: socket.socket):
            try:
                while True:
                    data = source.recv(8192)
                    if not data:
                        break
                    target.sendall(data)
            except Exception:
                pass
            finally:
                try:
                    source.close()
                except Exception:
                    pass
                try:
                    target.close()
                except Exception:
                    pass

        t1 = threading.Thread(target=forward, args=(client_sock, mysql_sock), daemon=True)
        t2 = threading.Thread(target=forward, args=(mysql_sock, client_sock), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except Exception:
        pass
    finally:
        try:
            client_sock.close()
        except Exception:
            pass


def main():
    print(f"[tunnel] Connecting to MySQL {MYSQL_HOST}:{MYSQL_PORT} ...", flush=True)
    mysql_conn = get_mysql_connection()
    print(f"[tunnel] Connected to MySQL {MYSQL_HOST}:{MYSQL_PORT}", flush=True)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen(20)
    print(f"[tunnel] Listening on {LISTEN_HOST}:{LISTEN_PORT}", flush=True)
    print("[tunnel] Press Ctrl+C to stop", flush=True)

    try:
        while True:
            client_sock, _ = server.accept()
            print("[tunnel] New local connection", flush=True)
            conn = mysql.connector.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE,
                ssl_disabled=False,
            )
            threading.Thread(
                target=handle_client,
                args=(client_sock, conn),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        print("\n[tunnel] Shutting down...", flush=True)
    finally:
        try:
            mysql_conn.close()
        except Exception:
            pass
        server.close()


if __name__ == "__main__":
    main()
