#!/usr/bin/env python3
"""Generate a weekly report from git log.

Reads recent commits (default: last 7 days) and renders a Chinese
weekly-report text, grouping commits by Conventional-Commits type
(feat/fix/docs/refactor/...).

Usage:
  python3 weekly_report.py                     # current repo, last 7 days
  python3 weekly_report.py -d 14               # last 14 days
  python3 weekly_report.py --author 张三        # only commits by 张三
  python3 weekly_report.py -o report.md        # also write to a file
  python3 weekly_report.py /path/to/repo1 /path/to/repo2
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from collections import OrderedDict

# Conventional-commit prefix -> Chinese category label
# (checked in order; first match wins)
CATEGORIES: list[tuple[str, str]] = [
    (r"^feat", "🆕 新增功能"),
    (r"^fix", "🐛 问题修复"),
    (r"^perf", "⚡ 性能优化"),
    (r"^refactor", "♻️ 重构"),
    (r"^docs", "📝 文档"),
    (r"^test", "🧪 测试"),
    (r"^style", "🎨 样式/格式"),
    (r"^ci", "🔧 CI/构建"),
    (r"^chore", "📦 杂项"),
]
OTHER = "📌 其他"

# Separator that cannot appear in commit subjects
SEP = "\x1f"


def run_git(repo: str, args: list[str]) -> str:
    """Run git in `repo` and return stdout ('' on failure)."""
    try:
        out = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True, text=True, check=False, timeout=30,
        )
        if out.returncode != 0:
            return ""
        return out.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def repo_name(repo: str) -> str:
    """Prefer the real work-tree directory name; fall back to the given path."""
    top = run_git(repo, ["rev-parse", "--show-toplevel"]).strip()
    if top:
        return top.rstrip("/").rsplit("/", 1)[-1]
    return repo


def collect(repo: str, days: int, author: str | None) -> dict:
    """Gather commits, line stats and metadata for one repository."""
    since = f"{days} days ago"

    fields = f"%h{SEP}%ad{SEP}%an{SEP}%s"
    log_args = [
        "log", f"--since={since}", "--no-merges", "--date=short",
        f"--pretty=format:{fields}",
    ]
    if author:
        log_args.append(f"--author={author}")

    raw = run_git(repo, log_args)
    commits: list[dict] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            h, date, who, subject = line.split(SEP)
        except ValueError:
            continue
        # strip a conventional-commit prefix like "feat(api): xxx"
        m = re.match(r"^(\w+)(\([^)]*\))?!?:\s*(.+)$", subject)
        if m:
            prefix, scope, clean = m.group(1), m.group(2) or "", m.group(3)
        else:
            prefix, scope, clean = "", "", subject
        commits.append({
            "hash": h, "date": date, "author": who,
            "prefix": prefix, "scope": scope, "subject": clean,
        })

    # total lines added/removed in the window
    stats = {"add": 0, "del": 0}
    if commits:
        for line in run_git(repo, ["log", f"--since={since}", "--no-merges",
                                  "--numstat", "--pretty=format:"]).splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                stats["add"] += int(parts[0])
                stats["del"] += int(parts[1])

    dates = [c["date"] for c in commits]
    return {
        "repo": repo,
        "name": repo_name(repo),
        "commits": commits,
        "stats": stats,
        "range": (min(dates), max(dates)) if dates else None,
    }


def categorize(prefix: str) -> str:
    """Map a commit prefix to a Chinese category label."""
    for pattern, label in CATEGORIES:
        if re.match(pattern, prefix):
            return label
    return OTHER


def render(results: list[dict], days: int) -> str:
    """Render the final weekly-report text."""
    today = dt.date.today().isoformat()
    start = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
    lines = [
        f"## 开发周报（{start} ~ {today}）",
        "",
    ]

    total_commits = sum(len(r["commits"]) for r in results)
    if total_commits == 0:
        lines.append("本周无提交记录。")
        return "\n".join(lines)

    tot_add = sum(r["stats"]["add"] for r in results)
    tot_del = sum(r["stats"]["del"] for r in results)
    lines.append(f"**总览**：{len(results)} 个仓库 · {total_commits} 次提交 · "
                 f"新增 {tot_add} 行 / 删除 {tot_del} 行")
    lines.append("")

    for r in results:
        if not r["commits"]:
            continue
        rng = r["range"]
        rng_txt = f"（{rng[0]} ~ {rng[1]}）" if rng else ""
        lines.append(f"### 仓库：`{r['name']}` {rng_txt}")
        lines.append(f"提交 {len(r['commits'])} 次 · 新增 {r['stats']['add']} / "
                     f"删除 {r['stats']['del']}")
        lines.append("")

        # group commits by category, keeping CATEGORIES order
        groups: OrderedDict[str, list[dict]] = OrderedDict(
            (label, []) for _, label in CATEGORIES)
        groups[OTHER] = []
        for c in r["commits"]:
            groups[categorize(c["prefix"])].append(c)

        for label, items in groups.items():
            if not items:
                continue
            lines.append(f"**{label}**")
            for c in sorted(items, key=lambda x: x["date"]):
                scope = f"`{c['scope']}` " if c["scope"] else ""
                lines.append(f"- {c['date']} {scope}{c['subject']} "
                             f"（{c['hash']}，{c['author']}）")
            lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"> 由 weekly_report.py 自动生成于 {today}")
    return "\n".join(lines).rstrip() + "\n"


def is_repo(repo: str) -> bool:
    """True if `repo` sits inside a git working tree."""
    return bool(run_git(repo, ["rev-parse", "--is-inside-work-tree"]).strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a weekly report from git log.")
    parser.add_argument("repos", nargs="*", default=["."],
                        help="repository paths (default: current directory)")
    parser.add_argument("-d", "--days", type=int, default=7,
                        help="look-back window in days (default: 7)")
    parser.add_argument("--author",
                        help="only include commits by this author (git --author syntax)")
    parser.add_argument("-o", "--output",
                        help="also write the report to this file")
    args = parser.parse_args()

    results = []
    for repo in args.repos:
        if not run_git(repo, ["rev-parse", "--is-inside-work-tree"]).strip():
            print(f"⚠️  跳过（不是 git 仓库）：{repo}", file=sys.stderr)
            continue
        results.append(collect(repo, args.days, args.author))

    report = render(results, args.days)
    print(report)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"✅ 已写入 {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
