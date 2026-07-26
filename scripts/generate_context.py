#!/usr/bin/env python3
"""
Generate architecture context for vllm by walking the local source tree and
reading key interface files, then using an LLM to synthesize a structured
JSON summary (data/vllm/context/architecture.json).

The context is injected into the daily analysis prompt so the AI understands
module boundaries instead of guessing. Weekly regeneration is recommended.
"""
import argparse
import json
import os
import sys
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_repo import ensure_repo, get_current_sha, repo_dir_name

TZ_CN = timezone(timedelta(hours=8))

IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "build", "dist", ".egg-info", ".mypy_cache", ".pytest_cache",
    ".hypothesis", ".tox", ".nox", ".direnv",
    ".github", ".buildkite", ".buildifier",
    "csrc",
}

SOURCE_DIR = "vllm"

# Key interface files that define the project's abstraction boundaries.
KEY_FILES = [
    # Platform & plugin
    "vllm/platforms/__init__.py",
    "vllm/platforms/interface.py",
    "vllm/plugins/__init__.py",
    # Engine core
    "vllm/v1/engine/core.py",
    "vllm/v1/engine/llm_engine.py",
    "vllm/v1/engine/core_client.py",
    # Executor & worker
    "vllm/v1/executor/abstract.py",
    "vllm/v1/worker/worker_base.py",
    "vllm/v1/worker/gpu_model_runner.py",
    # Attention
    "vllm/v1/attention/backend.py",
    "vllm/v1/attention/backends/registry.py",
    # Scheduler & KV cache
    "vllm/v1/core/scheduler.py",
    "vllm/v1/kv_cache_interface.py",
    # Spec decode
    "vllm/v1/spec_decode/eagle.py",
    # Quantization
    "vllm/model_executor/layers/quantization/__init__.py",
    # KV transfer (disaggregation / offloading)
    "vllm/distributed/kv_transfer/kv_connector/v1/base.py",
    # Config
    "vllm/config/vllm.py",
    # Model
    "vllm/model_executor/models/registry.py",
    "vllm/model_executor/models/interfaces_base.py",
    # Multimodal
    "vllm/multimodal/registry.py",
    # Compilation
    "vllm/compilation/compiler_interface.py",
    # Sampling
    "vllm/v1/sample/sampler.py",
    # Distributed
    "vllm/distributed/device_communicators/base_device_communicator.py",
    # Entrypoints
    "vllm/entrypoints/openai/serving_chat.py",
]

MAX_FILE_CHARS = 12000
MAX_TREE_DEPTH = 3

CONTEXT_PROMPT_TEMPLATE = """你是一个资深代码架构分析师。请根据以下项目源码结构目录树和关键接口文件内容，生成一份结构化的项目知识摘要。

## 仓库信息
- 仓库：{repo}
- 分支：main
- 分析的 commit：{commit_sha}

## 项目源码目录树
```
{tree}
```

## 关键接口文件内容
{key_files_content}

## 分析要求
请基于以上信息，分析以下内容：

1. **项目概述**：项目是什么、解决什么问题
2. **核心模块**：列出主要模块/目录及其职责，对于有技术深度的模块（如 Attention、Scheduler、KV Cache、Spec Decode、Quantization、Distributed），请在描述中包含**实现原理**
3. **关键抽象**：核心类/接口，要求包含：
   - inherits_from：该类/接口继承自哪个基类
   - key_methods：列出关键方法及其签名，简要说明作用
4. **实现原理**：针对核心模块/技术，描述其实现原理和技术细节，包括：
   - 它解决了什么问题
   - 核心工作流程（用文字描述即可，不要写代码）
   - 与其他模块的交互方式
   - 示例主题：EngineCore 调度循环、KV Cache 管理、GPUModelRunner 前向传播流程、投机解码流程、量化 dispatch 机制、PD 分离与 KV 传输、torch.compile 集成方式
5. **模块依赖关系**：模块间如何调用和依赖
6. **测试结构**：测试目录的组织方式

## 输出格式
输出 JSON 格式，不要输出其他内容：
```json
{{
  "repo": "{repo}",
  "generated_at": "<当前时间 UTC+8>",
  "commit_sha": "<commit SHA>",
  "overview": "<项目概述>",
  "modules": [
    {{
      "path": "<模块路径>",
      "name": "<模块名>",
      "description": "<职责描述（含实现原理，如适用）>",
      "key_classes": ["<类名>"]
    }}
  ],
  "key_abstractions": [
    {{
      "name": "<抽象名>",
      "description": "<描述>",
      "location": "<所在文件>",
      "inherits_from": "<继承的基类，没有则填 null>",
      "key_methods": ["<方法签名>: <作用简述>"],
      "relationships": ["<关联的抽象>"]
    }}
  ],
  "implementation_principles": [
    {{
      "module": "<模块名>",
      "problem": "<该模块解决的问题>",
      "workflow": "<核心工作流程的文字描述>",
      "interactions": "<与其他模块的交互方式>"
    }}
  ],
  "module_dependencies": "<模块依赖关系描述>",
  "test_structure": {{
    "path": "tests/",
    "description": "<测试组织方式>"
  }}
}}
```"""


def build_tree(repo_path, source_dir, max_depth=MAX_TREE_DEPTH):
    lines = []
    root = os.path.join(repo_path, source_dir)
    if not os.path.isdir(root):
        return "(source dir not found)"

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS)
        rel = os.path.relpath(dirpath, repo_path)
        depth = rel.count(os.sep)
        if depth >= max_depth:
            dirnames[:] = []
            continue
        indent = "  " * depth
        lines.append(f"{indent}{os.path.basename(dirpath)}/")
        if depth < max_depth - 1:
            for fn in sorted(filenames):
                if fn.endswith(".py"):
                    lines.append(f"{indent}  {fn}")
    return "\n".join(lines)


def read_key_files(repo_path):
    sections = []
    for rel_path in KEY_FILES:
        full = os.path.join(repo_path, rel_path)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(MAX_FILE_CHARS)
        except OSError:
            continue
        sections.append(f"### {rel_path}\n```python\n{content}\n```")
    return "\n\n".join(sections)


DEFAULT_API_BASE = "https://api.deepseek.com/v1"


def call_llm(prompt):
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("Error: LLM_API_KEY environment variable not set")
        return None

    api_base = os.environ.get("LLM_API_BASE", DEFAULT_API_BASE).rstrip("/")
    api_model = os.environ.get("LLM_MODEL", "deepseek-chat")

    print(f"  [call] prompt size: {len(prompt.encode('utf-8')):,} bytes")

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
        with urllib.request.urlopen(req, timeout=900) as resp:
            result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
        print(f"LLM API error: {e}")
        return None


def extract_json(output):
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
            parsed, _ = json.JSONDecoder().raw_decode(text, i)
            if isinstance(parsed, dict) and "overview" in parsed:
                return parsed
            i = text.find("{", i + 1)
        except (json.JSONDecodeError, ValueError):
            i = text.find("{", i + 1)
    return None


def save_json_atomic(filepath, data):
    dirpath = os.path.dirname(filepath)
    os.makedirs(dirpath, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dirpath, suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def generate_context(repo, data_dir, local_repo, force):
    context_path = os.path.join(data_dir, repo_dir_name(repo), "context", "architecture.json")

    if os.path.exists(context_path) and not force:
        print(f"Context already exists at {context_path} (use --force to regenerate)")
        return True

    if local_repo is None:
        print("Local repo unavailable, cannot generate context")
        return False

    commit_sha = get_current_sha(local_repo) or "unknown"
    print(f"Building source tree and key files for {repo} @ {commit_sha[:8]}...")

    tree = build_tree(local_repo, SOURCE_DIR)
    key_files_content = read_key_files(local_repo)

    prompt = CONTEXT_PROMPT_TEMPLATE.format(
        repo=repo,
        commit_sha=commit_sha,
        tree=tree,
        key_files_content=key_files_content,
    )

    print("Calling LLM to synthesize architecture context...")
    output = call_llm(prompt)
    if output is None:
        return False

    context = extract_json(output)
    if context is None:
        print("Failed to parse JSON from LLM output")
        return False

    context["repo"] = repo
    context["commit_sha"] = commit_sha
    context["generated_at"] = datetime.now(TZ_CN).isoformat()

    save_json_atomic(context_path, context)
    print(f"Context written to {context_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate vllm architecture context via LLM")
    parser.add_argument("--repo", default="vllm-project/vllm", help="GitHub repo (owner/repo)")
    parser.add_argument("--data-dir", default="data", help="Data directory")
    parser.add_argument("--local-repo", default=None, help="Path to local repo source code")
    parser.add_argument("--force", action="store_true", help="Force regenerate")
    args = parser.parse_args()

    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_repo = ensure_repo(args.repo, args.local_repo, project_dir)

    ok = generate_context(args.repo, args.data_dir, local_repo, args.force)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
