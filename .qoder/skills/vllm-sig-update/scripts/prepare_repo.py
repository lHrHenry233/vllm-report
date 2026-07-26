#!/usr/bin/env python3
"""Prepare a local shallow clone of vllm (repos/vllm) whose history covers
the meta.json anchor commit, so fetch_commits.py can use git log instead of
the GitHub API (no token needed).

Usage: python3 .qoder/skills/vllm-sig-update/scripts/prepare_repo.py
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

SKILL_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SKILL_SCRIPTS, "..", "..", "..", ".."))
REPO_DIR = os.path.join(PROJECT_ROOT, "repos", "vllm")
META_PATH = os.path.join(PROJECT_ROOT, "data", "vllm", "meta.json")
CLONE_URL = "https://github.com/vllm-project/vllm.git"


def run(cmd, cwd=None, timeout=1800):
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, timeout=timeout)


def load_meta():
    try:
        with open(META_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def compute_since(extra_days=7):
    """Shallow-clone window: meta last_fetch_time minus a buffer."""
    meta = load_meta()
    ts = meta.get("last_fetch_time", "")
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        dt = datetime.now()
    return (dt - timedelta(days=extra_days)).strftime("%Y-%m-%d")


def anchor_reachable():
    meta = load_meta()
    sha = meta.get("last_commit_sha", "")
    if not sha:
        return True  # no anchor yet, anything works
    r = subprocess.run(
        ["git", "cat-file", "-e", sha],
        cwd=REPO_DIR, capture_output=True,
    )
    return r.returncode == 0


def main():
    os.makedirs(os.path.dirname(REPO_DIR), exist_ok=True)
    since = compute_since()

    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        print(f"Cloning vllm (shallow since {since})...")
        r = run(["git", "clone", "--shallow-since", since, "--branch", "main",
                 CLONE_URL, REPO_DIR])
        if r.returncode != 0:
            print("Clone failed")
            sys.exit(1)
    else:
        print(f"Updating existing clone (shallow since {since})...")
        run(["git", "fetch", "--shallow-since", since, "origin", "main"], cwd=REPO_DIR)
        r = run(["git", "merge", "--ff-only", "origin/main"], cwd=REPO_DIR)
        if r.returncode != 0:
            print("ff-only merge failed, hard-resetting cache clone to origin/main")
            run(["git", "reset", "--hard", "origin/main"], cwd=REPO_DIR)

    # Ensure the anchor commit is inside the shallow window; deepen if not.
    for extra in (30, 90):
        if anchor_reachable():
            break
        older = compute_since(extra_days=extra)
        print(f"Anchor not reachable, deepening history to {older}...")
        run(["git", "fetch", "--shallow-since", older, "origin", "main"], cwd=REPO_DIR)

    if not anchor_reachable():
        print("WARNING: anchor commit still not reachable; fetch may fall back to API")
        sys.exit(2)

    print(f"Repo ready: {REPO_DIR}")


if __name__ == "__main__":
    main()
