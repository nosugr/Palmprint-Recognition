
"""一键启动：同时拉起 Flask 后端 + Vite 前端。

用法：
    python run.py

按 Ctrl+C 一次性关闭前后端两个进程。
后端默认 5000（config.py），前端 Vite 默认 5173，已在 vite.config.ts 把 /api、
/video_feed 代理到后端 5000，端口已对齐，无需手动设环境变量。
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
BACKEND_PORT = 5000
FRONTEND_PORT = 5173


def get_local_ip() -> str:
    """取本机局域网 IP，方便同网段其它设备访问。"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "本机IP"


def check_frontend_deps() -> bool:
    """前端依赖没装就别启动，给出明确提示。"""
    if (FRONTEND / "node_modules").is_dir():
        return True
    print("\n[错误] 前端依赖未安装。请先执行：")
    print(f"    cd {FRONTEND}")
    print("    npm install")
    print()
    return False


def start_backend() -> subprocess.Popen:
    """后端：python -m server.app，跑在项目根目录。"""
    return subprocess.Popen([sys.executable, "-m", "server.app"], cwd=str(ROOT))


def start_frontend() -> subprocess.Popen:
    """前端：npm run dev（Vite）。Windows 上 npm 是 npm.cmd，用 shell=True 走 PATH。"""
    return subprocess.Popen("npm run dev", cwd=str(FRONTEND), shell=True)


def stop(proc: subprocess.Popen) -> None:
    """结束进程及其子进程（Vite 会派生 esbuild 等子进程，需连带清理）。"""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> None:
    if not check_frontend_deps():
        sys.exit(1)

    local_ip = get_local_ip()
    print("\n" + "=" * 56)
    print("掌纹识别门禁系统  ·  一键启动")
    print("=" * 56)
    print("前端（在浏览器打开这个）：")
    print(f"  http://localhost:{FRONTEND_PORT}")
    print(f"  http://{local_ip}:{FRONTEND_PORT}   （局域网）")
    print()
    print(f"后端 API：http://localhost:{BACKEND_PORT}")
    print("按 Ctrl+C 关闭前后端。")
    print("=" * 56 + "\n")

    backend = start_backend()
    frontend = start_frontend()
    procs = [backend, frontend]

    try:
        # 任一进程退出就整体收摊，避免只剩半边在跑
        while True:
            for p in procs:
                if p.poll() is not None:
                    print(f"\n[提示] 某个进程已退出（code={p.returncode}），正在关闭另一个……")
                    raise KeyboardInterrupt
            try:
                backend.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
    except KeyboardInterrupt:
        print("\n正在关闭前后端……")
    finally:
        for p in procs:
            stop(p)
        print("已全部关闭。")


if __name__ == "__main__":
    # 让 Ctrl+C 只触发一次清理逻辑
    signal.signal(signal.SIGINT, signal.default_int_handler)
    main()
