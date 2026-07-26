#!/usr/bin/env python3
"""Validate an analysis JSON file against the commits data and SIG taxonomy.

Checks: required fields, every commit SHA covered exactly once, valid sig
ids, sig_summaries keys valid. Exit 0 with "OK" when valid.

Usage:
  python3 .qoder/skills/vllm-sig-update/scripts/validate_analysis.py --date YYYY-MM-DD
"""
import argparse
import json
import os
import sys

SKILL_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SKILL_SCRIPTS, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from sig_config import SIG_IDS  # noqa: E402

DATA_DIR = os.path.join(PROJECT_ROOT, "data", "vllm")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    commits_path = os.path.join(DATA_DIR, "commits", f"{args.date}.json")
    analysis_path = os.path.join(DATA_DIR, "analysis", f"{args.date}.json")

    errors = []

    try:
        with open(commits_path, encoding="utf-8") as fh:
            commits_data = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot load commits file: {e}")
        sys.exit(1)

    try:
        with open(analysis_path, encoding="utf-8") as fh:
            analysis = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot load analysis file: {e}")
        sys.exit(1)

    for field in ("date", "repo", "generated_at", "daily_summary", "commits"):
        if not analysis.get(field):
            errors.append(f"missing/empty top-level field: {field}")

    if analysis.get("date") != args.date:
        errors.append(f"date mismatch: {analysis.get('date')} != {args.date}")

    commit_shas = [c["sha"] for c in commits_data.get("commits", [])]
    analyzed = {}
    for ac in analysis.get("commits", []):
        sha = ac.get("sha", "")
        if sha in analyzed:
            errors.append(f"duplicate analysis for {sha[:8]}")
        analyzed[sha] = ac
        if sha not in commit_shas:
            errors.append(f"unknown sha {sha[:8]} (not in commits file)")
        if not ac.get("comment"):
            errors.append(f"{sha[:8]}: missing comment")
        if ac.get("sig") not in SIG_IDS:
            errors.append(f"{sha[:8]}: invalid sig {ac.get('sig')!r}")
        if not isinstance(ac.get("tags"), list) or not ac.get("tags"):
            errors.append(f"{sha[:8]}: missing/empty tags")

    for sha in commit_shas:
        if sha not in analyzed:
            errors.append(f"commit {sha[:8]} has no analysis entry")

    for sig in (analysis.get("sig_summaries") or {}):
        if sig not in SIG_IDS:
            errors.append(f"sig_summaries has invalid sig id: {sig}")

    if errors:
        print(f"FAIL ({len(errors)} errors):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print(f"OK: {len(commit_shas)} commits fully analyzed for {args.date}")


if __name__ == "__main__":
    main()
