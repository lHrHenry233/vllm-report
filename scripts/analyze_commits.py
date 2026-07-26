#!/usr/bin/env python3
"""Analyze daily vllm commits with an LLM and classify each commit into a
vLLM SIG (per the latest community Q3 roadmap, vllm-project/vllm#48168)."""
import argparse
import json
import os
import sys
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_repo import ensure_repo, repo_dir_name
from sig_config import (
    SIG_IDS,
    sig_name,
    build_sig_prompt_section,
    classify_by_paths,
    is_trivial_commit,
    triage_trivial_sig,
)

TZ_CN = timezone(timedelta(hours=8))

PROMPT_TEMPLATE = """你是一个 vLLM 代码变更分析专家。请对以下 commit 逐个进行分析。

## 仓库信息
- 仓库：{repo}
- 日期：{date}
- 分支：main

## 项目架构上下文
以下是该项目的架构摘要，请基于此上下文进行分析，避免对项目结构和模块关系进行猜测：
{context_section}

## vLLM SIG 分类体系
vLLM 社区将项目目标划分为多个 SIG（Special Interest Group，见 Q3 Roadmap #48168）。
每个 commit 必须归入且仅归入以下一个 SIG（取主要影响面）：

{sig_section}

归类原则：
1. 按 commit 的**主要意图和影响面**归类，而不是简单看文件路径
2. 涉及多个 SIG 时选择最核心的那个（如"给量化 kernel 提速"归 sig-quantization 而非 sig-model-performance）
3. 纯文档、示例、杂项归 other；CI/构建/测试基础设施归 sig-ci
4. 启发式预判仅供参考，如果你判断不同请以你的分析为准

## 待分析 commits
{commits_json}

## 分析要求
对每个 commit 逐一分析，输出以下内容：

1. **comment**：对该 commit 的分析评论（变更意图、实现方式、对 vLLM 的影响、潜在风险）。请参考架构上下文，准确判断变更涉及的模块和影响范围，不要硬猜
2. **sig**：SIG 分类 id，必须是以下之一：{sig_ids}
3. **sig_reason**：一句话说明归入该 SIG 的理由
4. **tags**：分类标签，从以下候选中选择或新增：
   - 类型：feature, bugfix, refactor, performance, docs, test, chore, ci
   - 风险：high-risk, medium-risk, low-risk
   - 模块：根据架构上下文中的模块定义标注（如 attention, scheduler, kv-cache, model-runner 等）

另外请提供以下摘要放在 JSON 顶层：

5. **daily_summary**：一段话总结当日 vLLM 变更的主要方向和重点
6. **sig_summaries**：对当日有变更的每个 SIG，用一两句话总结该 SIG 方向上的变更重点（对象，key 为 sig id，没有变更的 SIG 不要输出）

## 输出格式
严格输出以下 JSON 格式，不要输出任何其他内容：
```json
{{
  "date": "{date}",
  "repo": "{repo}",
  "generated_at": "<当前时间，UTC+8>",
  "daily_summary": "<当日整体摘要>",
  "sig_summaries": {{
    "sig-core": "<该 SIG 当日变更摘要>"
  }},
  "commits": [
    {{
      "sha": "<commit sha>",
      "comment": "<分析评论>",
      "sig": "<sig id>",
      "sig_reason": "<归类理由>",
      "tags": ["<tag1>", "<tag2>"]
    }}
  ]
}}
```"""


def load_json(filepath):
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to load {filepath}: {e}")
        return None


def save_json_atomic(filepath, data):
    dirpath = os.path.dirname(filepath)
    os.makedirs(dirpath, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dirpath, suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise e


def get_repo_dir(data_dir, repo):
    return os.path.join(data_dir, repo_dir_name(repo))


def get_latest_date(data_dir, repo):
    repo_dir = get_repo_dir(data_dir, repo)
    commits_dir = os.path.join(repo_dir, "commits")
    if not os.path.isdir(commits_dir):
        return None
    files = sorted(
        [f for f in os.listdir(commits_dir) if f.endswith(".json") and f != "meta.json"],
        reverse=True,
    )
    if not files:
        return None
    return files[0].replace(".json", "")


def load_commits_data(data_dir, repo, date):
    repo_dir = get_repo_dir(data_dir, repo)
    filepath = os.path.join(repo_dir, "commits", f"{date}.json")
    data = load_json(filepath)
    if data is None:
        print(f"No commit data found for {repo} on {date}")
        return None
    return data


def load_context(data_dir, repo):
    repo_dir = get_repo_dir(data_dir, repo)
    context_path = os.path.join(repo_dir, "context", "architecture.json")
    return load_json(context_path)


def build_context_section(context):
    if context is None:
        return '（未找到架构上下文文件，请基于 commit 内容和 diff 进行分析，对不确定的内容标注"不确定"）'

    parts = []
    if context.get("overview"):
        parts.append(f"项目概述：{context['overview']}")

    if context.get("modules"):
        modules_text = "\n".join(
            f"  - {m.get('path', '')} ({m.get('name', '')}): {m.get('description', '')}"
            for m in context["modules"]
        )
        parts.append(f"核心模块：\n{modules_text}")

    if context.get("key_abstractions"):
        abs_lines = []
        for a in context["key_abstractions"]:
            line = f"  - {a.get('name', '')} ({a.get('location', '')})"
            if a.get("inherits_from"):
                line += f" extends {a['inherits_from']}"
            line += f": {a.get('description', '')}"
            if a.get("key_methods"):
                methods = "; ".join(a["key_methods"])
                line += f"\n    关键方法: {methods}"
            abs_lines.append(line)
        parts.append("关键抽象：\n" + "\n".join(abs_lines))

    if context.get("implementation_principles"):
        principles_lines = []
        for p in context["implementation_principles"]:
            lines = [
                f"  [{p.get('module', '')}]",
                f"    问题: {p.get('problem', '')}",
                f"    流程: {p.get('workflow', '')}",
                f"    交互: {p.get('interactions', '')}",
            ]
            principles_lines.append("\n".join(lines))
        parts.append("实现原理：\n" + "\n".join(principles_lines))

    if context.get("module_dependencies"):
        parts.append(f"模块依赖：{context['module_dependencies']}")

    if context.get("test_structure"):
        ts = context["test_structure"]
        parts.append(f"测试结构：{ts.get('path', '')} - {ts.get('description', '')}")

    gen_time = context.get("generated_at", "unknown")
    parts.append(f"\n（上下文生成时间：{gen_time}，如需更详细信息请走读源码）")

    return "\n".join(parts)


def auto_analyze_commit(commit):
    """Generate a minimal analysis for a triaged trivial commit (docs/CI only)."""
    title = commit.get("message", "").split("\n")[0].lower()
    if any(w in title for w in ["fix", "bug", "hotfix"]):
        tags = ["bugfix", "low-risk"]
    elif any(w in title for w in ["feat", "add", "support", "implement"]):
        tags = ["feature", "low-risk"]
    elif any(w in title for w in ["refactor", "cleanup", "rename", "restruct"]):
        tags = ["refactor", "low-risk"]
    elif any(w in title for w in ["perf", "optimize", "speed"]):
        tags = ["performance", "low-risk"]
    elif any(w in title for w in ["doc", "readme"]):
        tags = ["docs"]
    else:
        tags = ["chore"]

    sig = triage_trivial_sig(commit)
    return {
        "sha": commit["sha"],
        "comment": "（自动判定）仅涉及 docs / examples / CI / 测试基础设施变更。",
        "sig": sig,
        "sig_reason": "（自动判定）变更文件均为文档或 CI/测试基础设施路径。",
        "tags": tags,
    }


def build_prompt(repo, date, commits_data, data_dir, commit_subset=None):
    context = load_context(data_dir, repo)
    context_section = build_context_section(context)

    commits_src = commits_data.get("commits", [])
    if commit_subset is not None:
        commits_src = [c for c in commits_src if c["sha"] in commit_subset]
        if not commits_src:
            return ""

    commits_for_prompt = []
    for c in commits_src:
        hint_sig, hint_conf = classify_by_paths(c)
        commit_info = {
            "sha": c["sha"],
            "message": c["message"],
            "author": c.get("author", {}),
            "stats": c.get("stats", {}),
            "sig_hint": {"sig": hint_sig, "confidence": hint_conf},
            "files": [],
        }
        for f in c.get("files", []):
            commit_info["files"].append({
                "filename": f["filename"],
                "status": f["status"],
                "additions": f["additions"],
                "deletions": f["deletions"],
                "patch": f.get("patch", ""),
            })
        commits_for_prompt.append(commit_info)

    commits_json = json.dumps(commits_for_prompt, ensure_ascii=False, indent=2)
    return PROMPT_TEMPLATE.format(
        repo=repo,
        date=date,
        commits_json=commits_json,
        context_section=context_section,
        sig_section=build_sig_prompt_section(),
        sig_ids=", ".join(SIG_IDS),
    )


DEFAULT_API_BASE = "https://api.deepseek.com/v1"


def call_llm(prompt):
    """Call the LLM API directly via environment variables.

    Required env var:
      LLM_API_KEY  — API key (e.g. DeepSeek sk-xxx)

    Optional env vars:
      LLM_API_BASE  — API base URL (default: https://api.deepseek.com/v1)
      LLM_MODEL     — model name sent to API (default: "deepseek-chat")
    """
    prompt_bytes = len(prompt.encode("utf-8"))
    print(f"  [call] prompt size: {prompt_bytes:,} bytes")

    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("Error: LLM_API_KEY environment variable not set")
        return None

    api_base = os.environ.get("LLM_API_BASE", DEFAULT_API_BASE).rstrip("/")
    api_model = os.environ.get("LLM_MODEL", "deepseek-chat")

    endpoint = f"{api_base}/chat/completions"
    body = json.dumps({
        "model": api_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 16384,
    }).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            result = json.loads(resp.read())
        content = result["choices"][0]["message"]["content"]
        if not content or not content.strip():
            print("LLM returned empty response")
            return None
        return content
    except urllib.error.HTTPError as e:
        print(f"API HTTP error: {e.code} {e.reason}")
        try:
            detail = e.read().decode("utf-8")
            print(f"  Response: {detail[:300]}")
        except Exception:
            pass
        return None
    except urllib.error.URLError as e:
        print(f"API connection error: {e.reason}")
        return None
    except json.JSONDecodeError as e:
        print(f"API returned invalid JSON: {e}")
        return None
    except KeyError as e:
        print(f"Unexpected API response format (missing {e})")
        return None


def extract_json_from_output(output):
    if not output:
        return None

    text = output.strip()
    if text.startswith("```"):
        start = text.find("\n")
        if start != -1:
            text = text[start:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()

    json_start = text.find("{")
    if json_start == -1:
        return None

    i = json_start
    while i != -1:
        try:
            parsed, end = json.JSONDecoder().raw_decode(text, i)
            if isinstance(parsed, dict) and "commits" in parsed:
                return parsed
            i = text.find("{", i + 1)
        except (json.JSONDecodeError, ValueError):
            i = text.find("{", i + 1)

    return None


def normalize_commit_analysis(ac, commit):
    """Ensure sig is valid; fall back to the path heuristic when missing."""
    sig = ac.get("sig")
    if sig not in SIG_IDS:
        fallback_sig, _ = classify_by_paths(commit) if commit else ("other", "low")
        ac["sig"] = fallback_sig
        ac.setdefault("sig_reason", "（回退）LLM 未给出有效 SIG，按文件路径启发式归类。")
    if "tags" not in ac or not isinstance(ac.get("tags"), list):
        ac["tags"] = ["chore"]
    if "comment" not in ac:
        ac["comment"] = "（分析缺失）"
    return ac


def validate_analysis(analysis, commits_data):
    errors = []

    if not isinstance(analysis, dict):
        return ["Analysis result is not a JSON object"]

    for field in ["date", "repo", "daily_summary", "commits"]:
        if field not in analysis:
            errors.append(f"Missing required field: {field}")

    if errors:
        return errors

    commit_shas = {c["sha"] for c in commits_data.get("commits", [])}

    for ac in analysis.get("commits", []):
        if "sha" not in ac:
            errors.append("Commit analysis missing 'sha' field")
            continue
        if ac["sha"] not in commit_shas:
            errors.append(f"SHA {ac['sha'][:8]} not found in commit data")
        if "comment" not in ac:
            errors.append(f"Commit {ac['sha'][:8]} missing field: comment")
        if "sig" not in ac:
            errors.append(f"Commit {ac['sha'][:8]} missing field: sig")
        elif ac["sig"] not in SIG_IDS:
            errors.append(f"Commit {ac['sha'][:8]} has invalid sig: {ac['sig']}")
        if "tags" not in ac:
            errors.append(f"Commit {ac['sha'][:8]} missing field: tags")

    return errors


def build_sig_summaries_fallback(merged_commits):
    """Count-based sig_summaries fallback when the LLM omits them."""
    counts = {}
    for ac in merged_commits:
        sig = ac.get("sig", "other")
        counts[sig] = counts.get(sig, 0) + 1
    return {
        sig: f"{sig_name(sig)} 方向当日共 {n} 条变更。"
        for sig, n in counts.items()
    }


def display_analysis(analysis):
    print("\n" + "=" * 60)
    print(f"Date: {analysis.get('date', 'N/A')}")
    print(f"Repo: {analysis.get('repo', 'N/A')}")
    print(f"\n📋 当日总结\n{analysis.get('daily_summary', 'N/A')}")

    sig_summaries = analysis.get("sig_summaries") or {}
    if sig_summaries:
        print("\n🏷 SIG 摘要")
        for sig, text in sig_summaries.items():
            print(f"  [{sig_name(sig)}] {text}")

    print(f"\nCommits analyzed: {len(analysis.get('commits', []))}")
    print("-" * 60)

    for ac in analysis.get("commits", []):
        sha_short = ac.get("sha", "")[:8]
        print(f"\n  [{sha_short}] {sig_name(ac.get('sig', 'other'))} {ac.get('tags', [])}")
        comment = ac.get("comment", "")
        print(f"  {comment[:200]}{'...' if len(comment) > 200 else ''}")

    print("=" * 60 + "\n")


def analyze_commits(repo, date, data_dir, confirm, force):
    commits_data = load_commits_data(data_dir, repo, date)
    if commits_data is None:
        print(f"No commit data for {repo} on {date}, skipping")
        return True

    all_commits = commits_data.get("commits", [])
    commits_by_sha = {c["sha"]: c for c in all_commits}
    num_commits = len(all_commits)
    if num_commits == 0:
        print(f"No commits found for {repo} on {date}, skipping")
        return True

    repo_dir = get_repo_dir(data_dir, repo)
    analysis_path = os.path.join(repo_dir, "analysis", f"{date}.json")

    if os.path.exists(analysis_path) and not force:
        if confirm:
            existing = load_json(analysis_path)
            if existing:
                print(f"Analysis already exists for {date}:")
                display_analysis(existing)
                answer = input("Overwrite? [y/N] ").strip().lower()
                if answer != "y":
                    print("Skipped.")
                    return True
        else:
            print(f"Analysis already exists for {date}, skipping (use --force to overwrite)")
            return True

    print(f"Analyzing {num_commits} commits for {repo} on {date}...")

    # Phase 1: triage — docs/CI-only commits skip the LLM
    llm_shas = []
    auto_analysis = []
    for c in all_commits:
        if is_trivial_commit(c):
            auto_analysis.append(auto_analyze_commit(c))
        else:
            llm_shas.append(c["sha"])

    if auto_analysis:
        print(f"  ├ {len(auto_analysis)} commits auto-classified (docs/CI only)")
    if llm_shas:
        print(f"  └ {len(llm_shas)} commits sent to LLM for analysis")

    # Phase 2: call LLM for the rest
    llm_analysis = None
    max_retries = 3
    retry_count = 0
    missing_shas = set()

    while llm_shas and retry_count < max_retries:
        llm_set = set(llm_shas)
        prompt = build_prompt(repo, date, commits_data, data_dir, commit_subset=llm_set)
        if not prompt:
            print("ERROR: empty prompt after subset filter")
            return False

        print(f"Calling LLM (attempt {retry_count + 1}, {len(llm_shas)} commits)...")
        output = call_llm(prompt)
        if output is None:
            print("Failed to get response from LLM")
            return False

        analysis = extract_json_from_output(output)
        if analysis is None:
            print("Failed to parse JSON from LLM output")
            print(f"Output length: {len(output)} chars")
            print(f"First 100 chars: {output[:100]!r}")
            dump_path = os.path.join(data_dir, "llm_raw_output.txt")
            try:
                with open(dump_path, "w", encoding="utf-8") as f:
                    f.write(output)
                print(f"Full raw output saved to: {dump_path}")
            except OSError:
                print("(could not save raw output to file)")
            return False

        # Accumulate LLM results across retries
        if llm_analysis is None:
            llm_analysis = analysis
        else:
            existing_shas = {ac["sha"] for ac in llm_analysis.get("commits", [])}
            for ac in analysis.get("commits", []):
                if ac["sha"] not in existing_shas:
                    llm_analysis["commits"].append(ac)
            # Merge sig_summaries from retries
            if analysis.get("sig_summaries"):
                llm_analysis.setdefault("sig_summaries", {}).update(analysis["sig_summaries"])

        analyzed_shas = {ac["sha"] for ac in llm_analysis.get("commits", [])}
        missing_shas = llm_set - analyzed_shas

        if not missing_shas:
            print(f"  ✓ All {len(llm_set)} commits analyzed")
            break

        print(f"  ⚠ {len(missing_shas)} commits missing from LLM response, retrying...")
        for sha in sorted(missing_shas):
            print(f"    - {sha[:8]}")

        llm_shas = list(missing_shas)
        retry_count += 1

    if missing_shas and retry_count >= max_retries:
        print(f"  ✗ Still {len(missing_shas)} commits missing after {max_retries} retries")

    analysis = llm_analysis

    if analysis and "commits" in analysis:
        for ac in analysis["commits"]:
            normalize_commit_analysis(ac, commits_by_sha.get(ac.get("sha")))
        errors = validate_analysis(analysis, commits_data)
        if errors:
            print("Validation errors:")
            for e in errors:
                print(f"  - {e}")
            if not confirm and not force:
                print("Analysis result invalid, not writing to file")
                return False
            if confirm:
                answer = input("Write anyway? [y/N] ").strip().lower()
                if answer != "y":
                    print("Skipped.")
                    return False

    # Phase 3: merge auto + LLM results, preserving commit order
    merged_shas = {}
    for ac in auto_analysis:
        merged_shas[ac["sha"]] = ac
    if analysis and "commits" in analysis:
        for ac in analysis["commits"]:
            merged_shas[ac["sha"]] = ac

    merged_commits = []
    for c in all_commits:
        ac = merged_shas.get(c["sha"])
        if ac:
            merged_commits.append(ac)
        else:
            fallback_sig, _ = classify_by_paths(c)
            merged_commits.append({
                "sha": c["sha"],
                "comment": "（分析缺失）",
                "sig": fallback_sig,
                "sig_reason": "（回退）按文件路径启发式归类。",
                "tags": ["chore"],
            })

    if analysis is None:
        analysis = {
            "date": date,
            "repo": repo,
            "daily_summary": f"当日 {len(auto_analysis)} 条 commit 均为文档 / CI / 测试基础设施变更。",
        }
    else:
        analysis["date"] = date
        analysis["repo"] = repo

    analysis["commits"] = merged_commits
    if not analysis.get("sig_summaries"):
        analysis["sig_summaries"] = build_sig_summaries_fallback(merged_commits)
    analysis["generated_at"] = datetime.now(TZ_CN).isoformat()

    if confirm:
        display_analysis(analysis)
        answer = input("Write this analysis to file? [Y/n] ").strip().lower()
        if answer == "n":
            print("Skipped.")
            return True

    save_json_atomic(analysis_path, analysis)
    print(f"Analysis written to {analysis_path}")
    return True


def get_unanalyzed_dates(data_dir, repo):
    repo_dir = get_repo_dir(data_dir, repo)
    commits_dir = os.path.join(repo_dir, "commits")
    analysis_dir = os.path.join(repo_dir, "analysis")

    if not os.path.isdir(commits_dir):
        return []

    commit_files = {
        f.replace(".json", "")
        for f in os.listdir(commits_dir)
        if f.endswith(".json") and f != "meta.json"
    }

    analyzed_files = set()
    if os.path.isdir(analysis_dir):
        analyzed_files = {
            f.replace(".json", "")
            for f in os.listdir(analysis_dir)
            if f.endswith(".json")
        }

    return sorted(commit_files - analyzed_files, reverse=True)


def main():
    parser = argparse.ArgumentParser(description="Analyze vllm commits using LLM with SIG classification")
    parser.add_argument("--repo", default="vllm-project/vllm", help="GitHub repo (owner/repo)")
    parser.add_argument("--date", default=None, help="Date to analyze (YYYY-MM-DD, UTC+8)")
    parser.add_argument("--latest", action="store_true", help="Analyze the latest date with commit data")
    parser.add_argument("--catch-up", action="store_true", help="Analyze all dates that have commits but no analysis")
    parser.add_argument("--confirm", action="store_true", help="Confirm before writing results")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing analysis")
    parser.add_argument("--data-dir", default="data", help="Data directory")
    args = parser.parse_args()

    if not args.date and not args.latest and not args.catch_up:
        args.catch_up = True

    dates_to_analyze = []
    if args.date:
        dates_to_analyze = [args.date]
    elif args.catch_up:
        dates_to_analyze = get_unanalyzed_dates(args.data_dir, args.repo)
        if not dates_to_analyze:
            print(f"All dates already analyzed for {args.repo}")
            sys.exit(0)
        print(f"Found {len(dates_to_analyze)} unanalyzed dates: {dates_to_analyze[-1]} ... {dates_to_analyze[0]}")
    elif args.latest:
        latest = get_latest_date(args.data_dir, args.repo)
        if latest is None:
            print(f"No commit data found for {args.repo}")
            sys.exit(1)
        dates_to_analyze = [latest]
        print(f"Latest date for {args.repo}: {latest}")

    success = True
    for date in dates_to_analyze:
        print(f"\n--- Analyzing {args.repo} / {date} ---")
        if not analyze_commits(args.repo, date, args.data_dir, args.confirm, args.force):
            success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
