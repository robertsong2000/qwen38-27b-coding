#!/usr/bin/env python3
"""Per-process CPU and memory monitor.

Pure standard library implementation (no psutil required).
Data source: `ps -axo pid,pcpu,pmem,rss,comm` (works on macOS and Linux).

Note: ps %CPU on macOS is a 1-minute average, not an instantaneous value.

Usage:
  python3 procm.py                    # top 10 processes by CPU
  python3 procm.py --by mem           # top 10 by memory instead
  python3 procm.py -n 20              # show top 20
  python3 procm.py -i 5               # refresh every 5 seconds, Ctrl+C to quit
  python3 procm.py -g python          # only processes whose name contains "python"
"""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import subprocess
import sys
import time

# ---------- helpers ----------


def run(cmd: list[str]) -> str:
    """Run a shell command and return stdout, or empty string on failure."""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def human(nbytes: float) -> str:
    """Format a byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if nbytes < 1024 or unit == "PB":
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


def color(percent: float, warn: int, crit: int) -> str:
    """Pick ANSI color: green < warn <= yellow < crit <= red."""
    if percent >= crit:
        return "\033[31m"  # red
    if percent >= warn:
        return "\033[33m"  # yellow
    return "\033[32m"  # green


RESET = "\033[0m"


# ---------- data collection ----------


class Proc:
    """One row of process usage data."""

    __slots__ = ("pid", "cpu", "mem_pct", "rss_bytes", "name")

    def __init__(self, pid: int, cpu: float, mem_pct: float,
                 rss_kb: int, name: str) -> None:
        self.pid = pid
        self.cpu = cpu
        self.mem_pct = mem_pct
        self.rss_bytes = rss_kb * 1024.0
        self.name = name


def collect(group: str | None) -> list[Proc]:
    """Snapshot all processes via ps; optionally filter by name substring."""
    out = run(["ps", "-axo", "pid,pcpu,pmem,rss,comm"])
    procs: list[Proc] = []
    for line in out.splitlines()[1:]:  # skip header
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        try:
            p = Proc(
                pid=int(parts[0]),
                cpu=float(parts[1]),
                mem_pct=float(parts[2]),
                rss_kb=int(parts[3]),
                name=parts[4].strip(),
            )
        except ValueError:
            continue  # malformed row, skip
        if group and group.lower() not in p.name.lower():
            continue
        procs.append(p)
    return procs


# ---------- display ----------


def snapshot(top: int, by: str, group: str | None) -> None:
    procs = collect(group)
    procs.sort(key=lambda p: p.cpu if by == "cpu" else p.mem_pct, reverse=True)
    procs = procs[:top]

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    total_rss = sum(p.rss_bytes for p in procs)
    print(f"\n=== {ts} ===  top {len(procs)} by {by.upper()}"
          + (f"  (name contains '{group}')" if group else ""))
    print(f"  {'PID':>6}  {'CPU%':>6}  {'MEM%':>6}  {'RSS':>9}  NAME")

    for p in procs:
        cc = color(p.cpu, 50, 90)          # color thresholds for CPU
        cm = color(p.mem_pct, 10, 20)      # ... and for memory
        name = p.name
        if len(name) > 40:
            name = name[:39] + "…"
        print(f"  {p.pid:>6}  {cc}{p.cpu:>6.1f}{RESET}  "
              f"{cm}{p.mem_pct:>6.1f}{RESET}  {human(p.rss_bytes):>9}  {name}")

    if procs:
        print(f"  {'':>6}  {'':>6}  {'':>6}  {human(total_rss):>9}  (sum of shown)")


# ---------- main ----------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Monitor per-process CPU and memory usage.")
    parser.add_argument("-n", "--top", type=int, default=10,
                        help="number of processes to show (default: 10)")
    parser.add_argument("--by", choices=("cpu", "mem"), default="cpu",
                        help="sort key (default: cpu)")
    parser.add_argument("-i", "--interval", type=float, default=0,
                        help="refresh interval in seconds; 0 = print once (default)")
    parser.add_argument("-g", "--group",
                        help="only show processes whose name contains this string")
    args = parser.parse_args()

    while True:
        try:
            snapshot(args.top, args.by, args.group)
        except KeyboardInterrupt:
            print("\nStopped.")
            break
        if args.interval <= 0:
            break
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
