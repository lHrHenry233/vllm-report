#!/usr/bin/env python3
"""Fetch PR descriptions for commits via GitHub API (gh CLI).

For each commit SHA in a date's commits JSON, fetches the associated
PR body via ``gh api repos/vllm-project/vllm/commits/{sha}/pulls``.
Results are stored in ``data/vllm/prs/<date>.json``.

The PR descriptions give the analyst (the agent) rich context — background,
design rationale, benchmark results — that is not present in the commit
message or diff alone.

Usage:
  python3 scripts/fetch_pr_descriptions.py [--date YYYY-MM-DD] [--force]

Requirements:
  - ``gh`` CLI authenticated (``gh auth status``).
  - ``data/vllm/commits/<date>.json`` must exist.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COMMITS_DIR = os.path.join(PROJECT_ROOT, "data", "vllm", "commits")
PRS_DIR = os.path.join(PROJECT_ROOT, "data", "vllm", "prs")
REPO = "vllm-project/vllm"
CST = timezone(timedelta(hours=8))


def gh_api(endpoint, jq=None, timeout=30):
    """Call ``gh api`` and return parsed JSON (or None on failure)."""
    cmd = ["gh", "api", endpoint]
    if jq:
        cmd += ["--jq", jq]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    if jq:
        try:
            return json.loads(r.stdout)
        except (json.JSONDecodeError, ValueError):
            return None
    try:
        return json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        return None


def fetch_pr_for_sha(sha):
    """Fetch the first (usually only) PR associated with *sha*."""
    pr = gh_api(
        f"repos/{REPO}/commits/{sha}/pulls",
        jq=".[0] | {number, title, body, html_url}",
    )
    if not pr or pr.get("number") is None:
        return None
    return pr


def dates_with_commits():
    """Return sorted list of dates that have commits but no PRs (or --force)."""
    if not os.path.isdir(COMMITS_DIR):
        return []
    commit_dates = {
        f[:-5] for f in os.listdir(COMMITS_DIR)
        if f.endswith(".json") and f != "meta.json"
    }
    return sorted(commit_dates)


def fetch_date(date, force=False):
    """Fetch PR descriptions for all commits on *date*."""
    commits_path = os.path.join(COMMITS_DIR, f"{date}.json")
    if not os.path.exists(commits_path):
        print(f"  {date}: no commits file, skipping")
        return

    prs_path = os.path.join(PRS_DIR, f"{date}.json")
    existing = {}
    if os.path.exists(prs_path) and not force:
        with open(prs_path, "r", encoding="utf-8") as fh:
            existing_data = json.load(fh)
            for entry in existing_data.get("commits", []):
                if entry.get("pr_number") is not None:
                    existing[entry["sha"]] = entry

    with open(commits_path, "r", encoding="utf-8") as fh:
        commits_data = json.load(fh)
    commits = commits_data.get("commits", [])

    results = []
    fetched = 0
    skipped = 0
    no_pr = 0

    for c in commits:
        sha = c["sha"]
        title = c.get("message", "").split("\n")[0]

        if sha in existing:
            results.append(existing[sha])
            skipped += 1
            continue

        pr = fetch_pr_for_sha(sha)
        if pr:
            entry = {
                "sha": sha,
                "pr_number": pr.get("number"),
                "pr_url": pr.get("html_url"),
                "pr_title": pr.get("title", ""),
                "pr_body": pr.get("body") or "",
            }
            fetched += 1
        else:
            entry = {
                "sha": sha,
                "pr_number": None,
                "pr_url": None,
                "pr_title": None,
                "pr_body": None,
            }
            no_pr += 1

        results.append(entry)
        # Small delay to avoid secondary rate limits.
        time.sleep(0.4)

    os.makedirs(PRS_DIR, exist_ok=True)
    out = {
        "date": date,
        "repo": REPO,
        "fetched_at": datetime.now(CST).isoformat(),
        "commits": results,
    }
    with open(prs_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"  {date}: {fetched} fetched, {skipped} cached, {no_pr} no-PR "
          f"(total {len(results)})")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch PR descriptions for vllm commits via gh CLI"
    )
    parser.add_argument("--date", default=None,
                        help="Fetch for a single date only (YYYY-MM-DD)")
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch even if PR data already exists")
    args = parser.parse_args()

    dates = [args.date] if args.date else dates_with_commits()
    if not dates:
        print("No dates with commit data found.")
        return

    print(f"Fetching PR descriptions for {len(dates)} date(s)...")
    for d in dates:
        fetch_date(d, force=args.force)
    print("Done.")


if __name__ == "__main__":
    main()
