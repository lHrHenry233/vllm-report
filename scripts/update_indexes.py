#!/usr/bin/env python3
"""Regenerate dates.json and analysis-dates.json indexes for the vllm repo.
Call after fetch/analysis completes."""
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_repo import repo_dir_name


def _write_index(repo_dir, filename, dates):
    idx_path = os.path.join(repo_dir, filename)
    fd, tmp_path = tempfile.mkstemp(dir=repo_dir, suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"dates": dates}, fh, indent=2)
        os.replace(tmp_path, idx_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _list_dates(dirpath):
    if not os.path.isdir(dirpath):
        return []
    return sorted(
        f.replace(".json", "")
        for f in os.listdir(dirpath)
        if f.endswith(".json") and re.match(r"^\d{4}-\d{2}-\d{2}$", f.replace(".json", ""))
    )


def update_indexes(data_dir, repo):
    repo_dir = os.path.join(data_dir, repo_dir_name(repo))
    if not os.path.isdir(repo_dir):
        return

    _write_index(repo_dir, "dates.json", _list_dates(os.path.join(repo_dir, "commits")))
    _write_index(repo_dir, "analysis-dates.json", _list_dates(os.path.join(repo_dir, "analysis")))


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data"
    repo = "vllm-project/vllm"
    update_indexes(data_dir, repo)
    print(f"Updated dates.json and analysis-dates.json for {repo}")


if __name__ == "__main__":
    main()
