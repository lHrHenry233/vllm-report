# vllm-sig-report

vLLM daily commit monitor with AI analysis, categorized by **vLLM SIG**
(Special Interest Group).

> **Attribution:** Based on [vllm-ascend/vllm-report](https://github.com/vllm-ascend/vllm-report).
> This version adds a local AI-driven SIG analysis workflow (Qoder skill),
> hybrid cloud-local automation, and independently generated analysis data.

SIG taxonomy follows the latest community roadmap
([\[Roadmap\] vLLM Roadmap Q3 2026 #48168](https://github.com/vllm-project/vllm/issues/48168)),
where vLLM's goals are broken down into SIGs (#32455):

| SIG id | Name | Scope |
| --- | --- | --- |
| `sig-core` | SIG Core | Scheduler, KV cache manager, model runner, Flat Model, frontend, tool calling, cold start |
| `sig-large-scale-serving` | SIG Large Scale Serving | PD disaggregation, KV offloading, KV events, EP/CP/DP, routing |
| `sig-model-performance` | SIG Model Performance | Kernels, attention backends, fused MoE, torch.compile, benchmarks |
| `sig-spec-decode` | SIG Spec Decode | EAGLE/MTP/DFlash/DFlare/DSpark, dynamic speculation, rejection sampler |
| `sig-quantization` | SIG Quantization | FP8/NVFP4/INT2-4, quantized KV cache, quant dispatch and fusion |
| `sig-omni` | vLLM-Omni | Multimodal / omni models, real-time interaction, video generation |
| `sig-rl` | RL Ecosystem | Weight sync, sleep mode, collective_rpc, RL framework integration |
| `sig-ci` | SIG CI | CI pipelines, test infra, build system, docker, release |
| `other` | Other | Docs, examples, misc chores |

## Features

- **Daily Commit Fetching** — fetches new vllm commits (with full diff) via
  GitHub Actions at 02:00 CST every day
- **AI SIG Analysis** — each commit is analyzed by an LLM (DeepSeek by
  default) for intent, risk, and assigned to exactly one SIG; a path-based
  heuristic pre-triages trivial commits and serves as fallback
- **Per-SIG Daily Summaries** — daily summary plus a one-liner per active SIG
- **Static Web Dashboard** — dark-themed page with SIG-grouped commit list,
  SIG distribution chart, SIG/tag filters, diff viewer, calendar, cross-day
  search, and Excel export
- **Architecture Context Cache** — weekly auto-generated vllm architecture
  summary injected into analysis prompts

## Project Structure

```
vllm-report/
├── .github/workflows/
│   ├── daily-commit.yml       # Daily fetch + AI SIG analysis
│   └── pages.yml              # GitHub Pages deployment
├── data/vllm/
│   ├── meta.json              # Anchor: latest SHA + last fetch time
│   ├── dates.json             # Commit date index
│   ├── analysis-dates.json    # Analysis date index
│   ├── commits/               # Daily commit JSON files
│   ├── analysis/              # Daily AI analysis results (SIG-based)
│   └── context/               # Architecture context cache
├── scripts/
│   ├── sig_config.py          # SIG definitions + path heuristics
│   ├── source_repo.py         # Local repo discovery/pull/clone
│   ├── fetch_commits.py       # Fetch commit data
│   ├── analyze_commits.py     # AI SIG analysis via LLM API
│   ├── generate_context.py    # Generate architecture context via LLM API
│   ├── update_indexes.py      # Refresh dates.json / analysis-dates.json
│   ├── migrate_reference_data.py  # One-off: import data from the reference repo
│   └── serve.py               # Local dev server
├── site/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── schemas/
    ├── commits-schema.json
    └── analysis-schema.json
```

## Quick Start

### 1. Fetch Commits

```bash
# Use GitHub API only
GITHUB_TOKEN=xxx python scripts/fetch_commits.py --api-only

# Or use a local vllm checkout (auto-detected at ~/code/vllm etc.)
python scripts/fetch_commits.py --local-repo ~/code/vllm
```

### 2. Set Up LLM API Key

```bash
export LLM_API_KEY="sk-你的DeepSeekAPIKey"
# Optional overrides:
# export LLM_API_BASE="https://api.deepseek.com/v1"
# export LLM_MODEL="deepseek-chat"
```

### 3. Generate Architecture Context (optional, recommended)

```bash
python scripts/generate_context.py --force
```

### 4. Run AI SIG Analysis

```bash
# Analyze all unanalyzed dates (default)
python scripts/analyze_commits.py

# Analyze a specific date / force overwrite
python scripts/analyze_commits.py --date 2026-07-24 --force

# Refresh indexes afterwards
python scripts/update_indexes.py
```

### 5. View Dashboard

```bash
python scripts/serve.py           # http://127.0.0.1:8765/site/index.html
```

## GitHub Actions Setup

Required secrets:

| Secret | Description |
| --- | --- |
| `DEEPSEEK_API_KEY` | API key for DeepSeek (or your LLM provider) |
| `GITHUB_TOKEN` | Default token (auto-provided) |

GitHub Pages: repo Settings → Pages → Source = "GitHub Actions".

## Data Format

### Commits (`data/vllm/commits/YYYY-MM-DD.json`)

Each commit includes: SHA, author, date, message, parents, stats, and full
diff per file.

### Analysis (`data/vllm/analysis/YYYY-MM-DD.json`)

Top level: `daily_summary`, `sig_summaries` (per-SIG one-liners). Each commit
analysis includes:

- `comment` — AI analysis of the change
- `sig` — primary SIG id (see table above)
- `sig_reason` — why the commit belongs to that SIG
- `tags` — type (feature/bugfix/...), risk (high/medium/low-risk), module

See `schemas/analysis-schema.json` for the full schema.
