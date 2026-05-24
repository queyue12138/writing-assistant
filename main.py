import uvicorn
import os
import sys
import socket
import webbrowser
import threading
import time
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.routers import chat, generate, feishu
from config import SERVER_HOST, SERVER_PORT, DEEPSEEK_API_KEY

app = FastAPI(title="Writing Assistant", version="1.1.0")

app.include_router(chat.router, prefix="/api")
app.include_router(generate.router, prefix="/api")
app.include_router(feishu.router, prefix="/api")

frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


@app.on_event("startup")
async def startup_feishu_polling():
    """Auto-start Feishu polling if credentials are configured."""
    from backend.feishu_event import get_config_status, start_polling
    status = get_config_status()
    if status["configured"]:
        print(f"[飞书Bot] 检测到已配置凭证 ({status['app_id_masked']})，自动启动轮询...")
        start_polling(interval=8)
        print("[飞书Bot] 轮询已启动（每8秒检查新消息）")
    else:
        print("[飞书Bot] 未配置凭证，跳过轮询启动。请在设置中填入 App ID/Secret。")


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def _kill_port(port: int):
    """Kill any process occupying the target port."""
    import subprocess
    try:
        result = subprocess.run(
            f'netstat -ano | findstr ":{port}.*LISTENING"',
            shell=True, capture_output=True, text=True
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 5:
                pid = parts[-1]
                subprocess.run(f"taskkill /F /PID {pid}", shell=True,
                             capture_output=True)
        time.sleep(1)
    except Exception:
        pass


if __name__ == "__main__":
    if not DEEPSEEK_API_KEY:
        print("\n" + "=" * 50)
        print("  WARNING: DEEPSEEK_API_KEY is not set!")
        print("  Please set the environment variable before running:")
        print("    set DEEPSEEK_API_KEY=sk-your-key")
        print("  Or edit the key directly in config.py")
        print("=" * 50 + "\n")

    # Kill old instance if any
    if _port_in_use(SERVER_HOST, SERVER_PORT):
        print("Port in use, closing old instance...")
        _kill_port(SERVER_PORT)
        if _port_in_use(SERVER_HOST, SERVER_PORT):
            print(f"ERROR: Cannot free port {SERVER_PORT}. Please restart your computer or close the program using it.")
            sys.exit(1)

    # Open browser after server starts
    def open_browser():
        time.sleep(1.5)
        url = f"http://{SERVER_HOST}:{SERVER_PORT}"
        print(f"Opening browser: {url}")
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    print(f"\n  Writing Assistant starting...")
    print(f"  Address: http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"  Press Ctrl+C to stop\n")

    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")
