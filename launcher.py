# -*- coding: utf-8 -*-
"""
刷题软件 - 启动器
=================
可选择使用「终端版」还是「网页版」，两套界面共用同一份题库/错题本数据。

用法:
    python launcher.py             # 显示选择菜单
    python launcher.py --web       # 直接启动网页版
    python launcher.py --cli       # 直接启动终端版
    python launcher.py web --port 9000
"""

import os
import sys


def _fix_console():
    """Windows 控制台 UTF-8 输出支持"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def show_menu():
    print("=" * 50)
    print("           刷题软件 - 启动器")
    print("=" * 50)
    print("  1. 终端版（命令行界面）")
    print("  2. 网页版（浏览器界面）")
    print("  0. 退出")
    print("=" * 50)


def run_web(port: int = None):
    """启动网页版"""
    try:
        from webui_server import start_server
    except ImportError as e:
        print(f"\n  ⚠️ 无法加载网页版模块: {e}")
        print("  请确认 webui_server.py 与 webui/ 目录存在。")
        return

    if port is None:
        try:
            port = int(os.environ.get("WEBUI_PORT", "8000"))
        except ValueError:
            port = 8000
    print("\n  正在启动网页版，首次启动会自动打开浏览器…")
    try:
        start_server(host="127.0.0.1", port=port, open_browser=True)
    except OSError as e:
        print(f"\n  ⚠️ 启动失败: {e}")
        print("  可能原因：端口被占用。可改用其它端口，例如：")
        print("      python launcher.py web --port 9000")


def run_cli():
    """启动终端版（原命令行界面）"""
    from menu import main_loop

    print("\n  正在进入终端版…")
    main_loop()


def main(argv):
    _fix_console()
    args = [a for a in argv]

    # 支持 python launcher.py web --port 9000
    direct = None
    port = None
    i = 0
    while i < len(args):
        if args[i] in ("--web", "web", "-w"):
            direct = "web"
        elif args[i] in ("--cli", "cli", "-c"):
            direct = "cli"
        elif args[i] == "--port" and i + 1 < len(args):
            try:
                port = int(args[i + 1])
            except ValueError:
                port = None
            i += 1
        i += 1

    if direct == "web":
        run_web(port)
        return
    if direct == "cli":
        run_cli()
        return

    while True:
        show_menu()
        try:
            choice = input("\n请输入编号: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            return

        if choice == "1":
            run_cli()
        elif choice == "2":
            run_web(port)
        elif choice == "0" or choice.lower() in ("exit", "quit"):
            print("再见！")
            return
        else:
            print("  无效选择，请输入 0-2。")


if __name__ == "__main__":
    main(sys.argv[1:])
