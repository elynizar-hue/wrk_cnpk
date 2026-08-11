import os
import socket
import ssl
import threading

MYSQL_HOST = os.getenv("MYSQL_HOST", "canpack-elynizar-dd70.h.aivencloud.com")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "10132"))
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "3306"))
LISTEN_HOST = os.getenv("LISTEN_HOST", "127.0.0.1")


def create_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def handle_client(client_sock: socket.socket, ssl_context: ssl.SSLContext):
    try:
        server_sock = socket.create_connection((MYSQL_HOST, MYSQL_PORT))
        server_ssl = ssl_context.wrap_socket(server_sock, server_hostname=MYSQL_HOST)

        def forward(source: socket.socket, target):
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

        t1 = threading.Thread(target=forward, args=(client_sock, server_ssl), daemon=True)
        t2 = threading.Thread(target=forward, args=(server_ssl, client_sock), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except Exception as e:
        print(f"[tunnel] Error: {e}", flush=True)
    finally:
        try:
            client_sock.close()
        except Exception:
            pass


def main():
    ssl_context = create_ssl_context()
    print(f"[tunnel] Starting SSL tunnel to {MYSQL_HOST}:{MYSQL_PORT}", flush=True)

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
            threading.Thread(
                target=handle_client,
                args=(client_sock, ssl_context),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        print("\n[tunnel] Shutting down...", flush=True)
    finally:
        server.close()


if __name__ == "__main__":
    main()
