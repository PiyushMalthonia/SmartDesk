import os
import socket

from app import app


def get_lan_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    lan_ip = get_lan_ip()
    print("SmartDesk AI is running.")
    print(f"Local URL:   http://127.0.0.1:{port}")
    print(f"Network URL: http://{lan_ip}:{port}")
    print("Open the Network URL on another device connected to the same Wi-Fi.")
    app.run(host="0.0.0.0", port=port, debug=False)
