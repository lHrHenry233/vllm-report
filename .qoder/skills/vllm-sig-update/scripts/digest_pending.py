#!/usr/bin/env python3
"""List dates that have commit data but no analysis, and print a compact
digest of each pending commit (title, stats, files, heuristic SIG hint).

The digest lets the agent analyze most commits without loading full diffs;
read data/vllm/commits/<date>.json selectively for ambiguous ones.

Usage:
  python3 .qoder/skills/vllm-sig-update/scripts/digest_pending.py [--date YYYY-MM-DD]
"""
import argparse
import json
import os
import sys

SKILL_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SKILL_SCRIPTS, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from sig_config import classify_by_paths, is_trivial_commit, triage_trivial_sig  # noqa: E402

COMMITS_DIR = os.path.join(PROJECT_ROOT, "data", "vllm", "commits")
ANALYSIS_DIR = os.path.join(PROJECT_ROOT, "data", "vllm", "analysis")


def pending_dates():
    commits = {
        f[:-5] for f in os.listdir(COMMITS_DIR)
        if f.endswith(".json") and f != "meta.json"
    }
    analyzed = set()
    if os.path.isdir(ANALYSIS_DIR):
        analyzed = {f[:-5] for f in os.listdir(ANALYSIS_DIR) if f.endswith(".json")}
    return sorted(commits - analyzed)


def top_dirs(files, n=6):
    seen = []
    for f in files:
        parts = f.get("filename", "").split("/")
        key = "/".join(parts[:3]) if len(parts) > 3 else f.get("filename", "")
        if key not in seen:
            seen.append(key)
    extra = len(seen) - n
    return ", ".join(seen[:n]) + (f" (+{extra} more)" if extra > 0 else "")


def digest_date(date):
    path = os.path.join(COMMITS_DIR, f"{date}.json")
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    commits = data.get("commits", [])
    print(f"\n=== {date}: {len(commits)} commits ===")
    for c in commits:
        sha = c["sha"]
        title = c.get("message", "").split("\n")[0]
        stats = c.get("stats", {})
        files = c.get("files", [])
        if is_trivial_commit(c):
            hint, conf = triage_trivial_sig(c), "trivial"
        else:
            hint, conf = classify_by_paths(c)
        print(f"\n- sha: {sha}")
        print(f"  title: {title}")
        print(f"  stats: +{stats.get('total_additions', 0)}/-{stats.get('total_deletions', 0)} files={stats.get('files_changed', 0)}")
        print(f"  paths: {top_dirs(files)}")
        print(f"  sig_hint: {hint} ({conf})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Digest a single date only")
    args = parser.parse_args()

    dates = [args.date] if args.date else pending_dates()
    if not dates:
        print("No pending dates. All commit data is analyzed.")
        return
    print("Pending dates:", ", ".join(dates))
    for d in dates:
        digest_date(d)


if __name__ == "__main__":
    main()
