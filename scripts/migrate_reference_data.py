#!/usr/bin/env python3
"""One-off migration: convert vllm data from the reference vllm-report repo
(ascend-oriented analysis) into this project's SIG-based format.

- commits/*.json are copied unchanged (same schema).
- analysis/*.json: ascend_impact fields are dropped; each commit gains a
  `sig` assigned by the path heuristic (LLM re-analysis can refine later
  via analyze_commits.py --force).
- context/architecture.json is copied with ascend-specific fields stripped.

Usage:
  python scripts/migrate_reference_data.py --src ref/vllm-report/data/vllm --dst data/vllm
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sig_config import classify_by_paths, sig_name


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def migrate_commits(src_dir, dst_dir):
    src = os.path.join(src_dir, "commits")
    dst = os.path.join(dst_dir, "commits")
    os.makedirs(dst, exist_ok=True)
    count = 0
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".json"):
            continue
        shutil.copy2(os.path.join(src, fn), os.path.join(dst, fn))
        count += 1
    print(f"Copied {count} commit files")


def migrate_analysis(src_dir, dst_dir):
    src = os.path.join(src_dir, "analysis")
    dst = os.path.join(dst_dir, "analysis")
    os.makedirs(dst, exist_ok=True)
    count = 0
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".json"):
            continue
        analysis = load_json(os.path.join(src, fn))
        if analysis is None:
            continue

        date = fn.replace(".json", "")
        commits_data = load_json(os.path.join(src_dir, "commits", fn)) or {}
        commits_by_sha = {c["sha"]: c for c in commits_data.get("commits", [])}

        new_commits = []
        sig_counts = {}
        for ac in analysis.get("commits", []):
            commit = commits_by_sha.get(ac.get("sha"), {})
            sig, _conf = classify_by_paths(commit)
            new_ac = {
                "sha": ac.get("sha", ""),
                "comment": ac.get("comment", ""),
                "sig": sig,
                "sig_reason": "（启发式迁移）按变更文件路径归类，可用 analyze_commits.py --force 重新分析。",
                "tags": ac.get("tags", []),
            }
            new_commits.append(new_ac)
            sig_counts[sig] = sig_counts.get(sig, 0) + 1

        sig_summaries = {
            sig: f"{sig_name(sig)} 方向当日共 {n} 条变更。"
            for sig, n in sorted(sig_counts.items(), key=lambda kv: -kv[1])
        }

        new_analysis = {
            "date": analysis.get("date", date),
            "repo": analysis.get("repo", "vllm-project/vllm"),
            "generated_at": analysis.get("generated_at", ""),
            "daily_summary": analysis.get("daily_summary", ""),
            "sig_summaries": sig_summaries,
            "commits": new_commits,
        }
        save_json(os.path.join(dst, fn), new_analysis)
        count += 1
    print(f"Migrated {count} analysis files")


def migrate_context(src_dir, dst_dir):
    src_path = os.path.join(src_dir, "context", "architecture.json")
    context = load_json(src_path)
    if context is None:
        print("No architecture context to migrate")
        return

    # Strip ascend/cross-project specific fields
    for key in ("cross_project_relationship", "interface_surface", "hardware_abstraction"):
        context.pop(key, None)
    for a in context.get("key_abstractions", []):
        a.pop("ascend_implementations", None)
    for p in context.get("implementation_principles", []):
        p.pop("platform_differences", None)

    save_json(os.path.join(dst_dir, "context", "architecture.json"), context)
    print("Migrated architecture context (ascend fields stripped)")


def migrate_meta(src_dir, dst_dir):
    meta = load_json(os.path.join(src_dir, "meta.json"))
    if meta:
        save_json(os.path.join(dst_dir, "meta.json"), meta)
        print("Copied meta.json")


def main():
    parser = argparse.ArgumentParser(description="Migrate reference vllm-report data to SIG format")
    parser.add_argument("--src", required=True, help="Source data dir (e.g. ref/vllm-report/data/vllm)")
    parser.add_argument("--dst", default="data/vllm", help="Destination data dir")
    args = parser.parse_args()

    if not os.path.isdir(args.src):
        print(f"Source dir not found: {args.src}")
        sys.exit(1)

    migrate_commits(args.src, args.dst)
    migrate_analysis(args.src, args.dst)
    migrate_context(args.src, args.dst)
    migrate_meta(args.src, args.dst)
    print("Done. Now run: python scripts/update_indexes.py")


if __name__ == "__main__":
    main()
