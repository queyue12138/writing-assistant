"""写作助手启动器 — 双击此文件启动，关闭窗口即停止"""
import subprocess
import sys
import os
import time
import threading
import webbrowser

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=" * 50)
print("  写作助手")
print("=" * 50)

# 1. 安装依赖
print("[1/3] 检查依赖...")
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
    capture_output=True,
)

# 2. 清理旧进程
print("[2/3] 清理旧进程...")
try:
    result = subprocess.run(
        'netstat -ano | findstr ":8765.*LISTENING"',
        shell=True, capture_output=True, text=True,
    )
    for line in result.stdout.strip().split("\n"):
        parts = line.split()
        if len(parts) >= 5:
            subprocess.run(["taskkill", "/F", "/PID", parts[-1]], capture_output=True)
    time.sleep(0.5)
except Exception:
    pass

# 3. 启动
print("[3/3] 启动服务...")
print("  地址: http://127.0.0.1:8765")
print("  关闭此窗口即停止服务")
print("=" * 50)

def open_browser():
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8765")

threading.Thread(target=open_browser, daemon=True).start()

# 直接启动服务器
from main import app
from config import SERVER_HOST, SERVER_PORT
import uvicorn
uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")
