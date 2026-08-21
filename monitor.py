#!/usr/bin/env python3
"""System resource monitor: CPU, memory and disk usage.

Pure standard library implementation (no psutil required).
Data sources per platform:
  - macOS:  top / sysctl / df
  - Linux:  /proc/stat, /proc/meminfo, df
  - Windows: not supported (install psutil and adapt if needed)

Usage:
  python3 monitor.py                # refresh every 2 seconds, Ctrl+C to quit
  python3 monitor.py --once         # single snapshot then exit
  python3 monitor.py -i 5           # refresh every 5 seconds
  python3 monitor.py --threshold 90 # warn when any metric >= 90%
"""

from __future__ import annotations

import argparse
import platform
import re
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


def bar(percent: float, width: int = 25) -> str:
    """Render a textual progress bar, e.g. [#####..........] 23.5%"""
    filled = int(round(width * percent / 100.0))
    filled = max(0, min(width, filled))
    return f"[{'#' * filled}{'.' * (width - filled)}] {percent:5.1f}%"


def color(percent: float, warn: int, crit: int) -> str:
    """Pick ANSI color: green < warn <= yellow < crit <= red."""
    if percent >= crit:
        return "\033[31m"  # red
    if percent >= warn:
        return "\033[33m"  # yellow
    return "\033[32m"  # green


RESET = "\033[0m"


def human(nbytes: float) -> str:
    """Format a byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if nbytes < 1024 or unit == "PB":
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


# ---------- macOS collectors ----------


def cpu_macos() -> float:
    """Overall CPU usage percent from `top -l 1 -n 0`."""
    out = run(["top", "-l", "1", "-n", "0"])
    m = re.search(r"CPU usage: [\d.]+% user, [\d.]+% sys, ([\d.]+)% idle", out)
    if m:
        return 100.0 - float(m.group(1))
    return -1.0  # unknown


def memory_macos() -> tuple[float, float, float]:
    """Return (used_mb, total_mb, percent).

    Uses the "PhysMem: X used" line from `top`, which matches what
    Activity Monitor reports (wired + active + compressed, excluding
    inactive/purgeable pages that are still reclaimable).
    """
    out = run(["top", "-l", "1", "-n", "0"])
    total_bytes = int(run(["sysctl", "-n", "hw.memsize"]).strip() or 0)
    m = re.search(r"PhysMem:\s*(\d+)([KMGT])B?\s+used", out)
    if not m or total_bytes <= 0:
        return -1.0, -1.0, -1.0
    mult = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}[m.group(2)]
    used_bytes = int(m.group(1)) * mult
    return used_bytes / 1e6, total_bytes / 1e6, used_bytes / total_bytes * 100.0


# ---------- Linux collectors ----------


def cpu_linux() -> float:
    """CPU usage from the delta between two /proc/stat samples."""

    def sample() -> tuple[float, float]:
        with open("/proc/stat") as f:
            parts = f.readline().split()[1:]
        nums = [int(x) for x in parts]
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)  # idle + iowait
        total = sum(nums)
        return idle, total

    idle1, total1 = sample()
    time.sleep(0.5)
    idle2, total2 = sample()
    dt = total2 - total1
    if dt <= 0:
        return -1.0
    return (1.0 - (idle2 - idle1) / dt) * 100.0


def memory_linux() -> tuple[float, float, float]:
    """Return (used_mb, total_mb, percent) from /proc/meminfo."""
    info: dict[str, int] = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            info[k] = int(v.strip().split()[0])  # value in kB
    total = info.get("MemTotal", 0)
    # used = total - free - buffers - cache (convention used by `free`)
    used = total - info.get("MemFree", 0) - info.get("Buffers", 0) - info.get("Cached", 0)
    if total <= 0:
        return -1.0, -1.0, -1.0
    return used / 1024.0, total / 1024.0, used / total * 100.0


# ---------- cross-platform disk (df) ----------


def disk(path: str = "/") -> tuple[float, float, float]:
    """Return (used_mb, total_mb, percent) for the given mount path via `df`."""
    out = run(["df", "-k", path])
    lines = out.strip().splitlines()
    if len(lines) < 2:
        return -1.0, -1.0, -1.0
    fields = lines[-1].split()
    if len(fields) < 5:
        return -1.0, -1.0, -1.0
    total_kb = int(fields[1])
    used_kb = int(fields[2])
    if total_kb <= 0:
        return -1.0, -1.0, -1.0
    percent = used_kb / total_kb * 100.0
    return used_kb / 1024.0, total_kb / 1024.0, percent


# ---------- platform dispatch ----------


def get_cpu() -> float:
    if platform.system() == "Darwin":
        return cpu_macos()
    if platform.system() == "Linux":
        return cpu_linux()
    return -1.0


def get_memory() -> tuple[float, float, float]:
    if platform.system() == "Darwin":
        return memory_macos()
    if platform.system() == "Linux":
        return memory_linux()
    return -1.0, -1.0, -1.0


# ---------- display ----------


def snapshot(disk_path: str, threshold: float) -> None:
    cpu = get_cpu()
    mem_used, mem_total, mem_pct = get_memory()
    disk_used, disk_total, disk_pct = disk(disk_path)

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n=== {ts} ===")

    if cpu >= 0:
        c = color(cpu, 70, 90)
        print(f"  CPU    {c}{bar(cpu)}{RESET}")
    else:
        print("  CPU    (unavailable on this platform)")

    if mem_pct >= 0:
        c = color(mem_pct, 80, 95)
        print(f"  Memory {c}{bar(mem_pct)}{RESET}  {human(mem_used * 1e6)} / {human(mem_total * 1e6)}")
    else:
        print("  Memory (unavailable on this platform)")

    if disk_pct >= 0:
        c = color(disk_pct, 85, 95)
        print(f"  Disk{disk_path:<22} {c}{bar(disk_pct)}{RESET}  {human(disk_used * 1e6)} / {human(disk_total * 1e6)}")
    else:
        print("  Disk   (unavailable)")

    # Threshold warnings (for scripting / alerting use cases)
    for name, pct in (("CPU", cpu), ("Memory", mem_pct), ("Disk", disk_pct)):
        if pct >= 0 and pct >= threshold:
            print(f"  !! WARNING: {name} usage {pct:.1f}% >= {threshold:.0f}%")


# ---------- main ----------


def main() -> int:
    # On macOS, `/` is the small read-only system snapshot volume;
    # the real user data volume is /System/Volumes/Data.
    default_disk = "/System/Volumes/Data" if platform.system() == "Darwin" else "/"

    parser = argparse.ArgumentParser(description="Monitor CPU, memory and disk usage.")
    parser.add_argument("-i", "--interval", type=float, default=2.0,
                        help="refresh interval in seconds (default: 2)")
    parser.add_argument("--once", action="store_true",
                        help="print one snapshot and exit")
    parser.add_argument("--disk-path", default=default_disk,
                        help=f"filesystem path to monitor (default: {default_disk})")
    parser.add_argument("--threshold", type=float, default=95.0,
                        help="print a WARNING when any metric exceeds this percent")
    args = parser.parse_args()

    while True:
        snapshot(args.disk_path, args.threshold)
        if args.once:
            break
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
