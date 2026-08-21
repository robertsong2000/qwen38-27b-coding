#!/usr/bin/env python3
"""macOS notification helper built on `osascript display notification`.

Pure standard library, macOS only (osascript is AppleScript).

The script is fed to `osascript` via stdin, so no shell-quoting issues.

Usage:
  python3 notify.py "下载完成，共 100 条" -t 爬虫        # basic notification
  python3 notify.py "构建成功" -t CI -s Glass           # with a system sound
  python3 notify.py "任务完成" -t 构建 -u "耗时 3 分 20 秒"  # with subtitle
  python3 notify.py -c "python3 crawler.py" -t 爬虫     # notify when a command
                                                        # finishes (ok/fail)
  python3 notify.py --demo                              # try the features one by one
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
import time

# System sounds accepted by `display notification ... sound name ...`
SOUNDS = ["default", "Basso", "Glass", "Hero", "Morse",
          "Ping", "Purr", "Sosumi", "Subtle", "Tink"]


def die(msg: str) -> None:
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def require_macos() -> None:
    if platform.system() != "Darwin":
        die("display notification 只在 macOS 上可用（依赖 osascript）")


def aquote(s: str) -> str:
    """Escape a Python string into a double-quoted AppleScript literal."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def send(message: str,
         title: str = "脚本",
         subtitle: str | None = None,
         sound: str | None = None) -> None:
    """Send one macOS notification and return once osascript accepts it."""
    parts = [f"display notification {aquote(message)}",
             f"with title {aquote(title)}"]
    if subtitle:
        parts.append(f"subtitle {aquote(subtitle)}")
    if sound:
        parts.append(f"sound name {aquote(sound)}")

    try:
        subprocess.run(["osascript"], input=" ".join(parts) + "\n",
                       text=True, check=True, capture_output=True, timeout=10)
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or "").strip()
        die(f"osascript 执行失败：{detail}")
    except FileNotFoundError:
        die("找不到 osascript，请确认在 macOS 上运行")


def run_command(cmd: str, title: str,
                success_sound: str | None, fail_sound: str | None) -> int:
    """Run a shell command; notify on success/failure. Returns its exit code."""
    print(f"⏳ 运行中：{cmd}")
    try:
        proc = subprocess.run(["/bin/sh", "-c", cmd],
                              capture_output=True, text=True, timeout=3600)
    except subprocess.TimeoutExpired:
        send("命令超时（1 小时）被终止", f"❌ {title}", sound=fail_sound)
        return 124

    if proc.returncode == 0:
        send("命令执行成功", f"✅ {title}", sound=success_sound)
    else:
        # last stderr line is usually the most useful bit
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        msg = tail[-1][:200] if tail else f"退出码 {proc.returncode}"
        send(msg, f"❌ {title}", sound=fail_sound)
    return proc.returncode


def demo() -> None:
    """Fire a few notifications with a short pause so they show one by one."""
    send("下载完成，共 100 条数据", "🕷️ 爬虫", subtitle="耗时 42 秒")
    time.sleep(1.5)
    send("第 3 步构建成功", "🔨 CI", subtitle="deploy-api @ main")
    time.sleep(1.5)
    send("备份完成（2.3 GB）", "💾 备份", sound="Glass")
    time.sleep(1.5)
    rc = run_command("sleep 3", "模拟长任务", success_sound="Ping",
                     fail_sound=None)
    print(f"demo 结束（模拟长任务退出码 {rc}）")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send a macOS notification via osascript.")
    parser.add_argument("message", nargs="?",
                        help="notification body (omit when using -c or --demo)")
    parser.add_argument("-t", "--title", default="脚本",
                        help="notification title (default: 脚本)")
    parser.add_argument("-u", "--subtitle",
                        help="optional subtitle line")
    parser.add_argument("-s", "--sound", choices=SOUNDS,
                        help="system sound to play (default: none)")
    parser.add_argument("-c", "--command", metavar="CMD",
                        help="run this shell command and notify when it finishes")
    parser.add_argument("--demo", action="store_true",
                        help="fire a sequence of example notifications")
    args = parser.parse_args()

    require_macos()

    if args.demo:
        demo()
        return 0

    if args.command:
        return run_command(args.command, args.title, args.sound,
                           "Basso" if args.sound is None else args.sound)

    if not args.message:
        parser.print_usage(sys.stderr)
        die("缺少通知内容：请给 message，或用 -c / --demo")

    send(args.message, args.title, args.subtitle, args.sound)
    return 0


if __name__ == "__main__":
    sys.exit(main())
