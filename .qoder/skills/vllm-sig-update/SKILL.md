---
name: vllm-sig-update
description: Fetch the latest vllm-project/vllm commits, analyze each one with AI, classify by vLLM SIG, and refresh the vLLM SIG Monitor dashboard data — all without any API keys (uses a local git clone; the agent itself performs the AI analysis). Use when the user asks to update vllm commits, refresh the vllm report/dashboard, sync today's vllm community changes, or fill in missing (pending) commit analysis. Trigger phrases include "更新 vllm commit", "更新今天 vllm 社区的 commit", "刷新 vllm 报告", "补分析", "update vllm report".
---

# vLLM SIG Update (closed-loop, no API keys)

Updates the vLLM SIG Monitor: fetch new commits via a local git clone,
then the agent (you) performs the AI SIG analysis and writes the result
JSON directly. Do NOT call `scripts/analyze_commits.py` (it needs
LLM_API_KEY); you replace its LLM step.

All commands run from the project root (`cd` to the repo root first).

## Workflow

```
Task Progress:
- [ ] Step 1: Prepare local vllm clone
- [ ] Step 2: Fetch new commits
- [ ] Step 3: Fetch PR descriptions
- [ ] Step 4: Digest pending dates
- [ ] Step 5: Write analysis JSON per date (agent = the AI)
- [ ] Step 6: Validate each analysis file
- [ ] Step 7: Update indexes + refresh dashboard
- [ ] Step 8: (optional) commit & push
```

### Step 1: Prepare local vllm clone

```bash
python3 .qoder/skills/vllm-sig-update/scripts/prepare_repo.py
```

Shallow-clones/updates `repos/vllm` so history covers the anchor SHA in
`data/vllm/meta.json`. First clone downloads a few hundred MB; be patient
(run with a generous timeout or in background). Exit 2 = anchor
unreachable — deepen manually with
`git -C repos/vllm fetch --shallow-since <earlier-date> origin main`.

### Step 2: Fetch new commits

```bash
python3 scripts/fetch_commits.py --local-repo repos/vllm
```

Writes `data/vllm/commits/<date>.json` per day and advances the anchor in
`meta.json`. Never use `--api-only` without GITHUB_TOKEN: anonymous quota
(60/h) makes the script sleep forever on its rate-limit guard.

### Step 3: Fetch PR descriptions

```bash
python3 scripts/fetch_pr_descriptions.py --date <date>
```

Fetches the PR body (background, design rationale, benchmark results)
for each commit via `gh api`. Stores results in
`data/vllm/prs/<date>.json`. Requires `gh` authenticated. Run for each
pending date (or omit `--date` for all dates with commits).
Already-fetched PRs are cached; use `--force` to re-fetch.

### Step 4: Digest pending dates

```bash
python3 .qoder/skills/vllm-sig-update/scripts/digest_pending.py
```

Prints unanalyzed dates and, per commit: sha, title, stats, top paths, and
a heuristic `sig_hint`. If the user asked for a specific date only, add
`--date YYYY-MM-DD`.

### Step 5: Write analysis JSON (you are the analyst)

For each pending date, write `data/vllm/analysis/<date>.json`:

```json
{
  "date": "<date>",
  "repo": "vllm-project/vllm",
  "generated_at": "<now, ISO 8601 UTC+8>",
  "daily_summary": "<当日整体摘要，结构化 markdown：今日概览 / 今日重点（平台→模型两层）/ 需要关注，总长约 800-1400 字>",
  "sig_summaries": { "<sig-id>": "<该 SIG 当日变更重点，中文 3-5 句、约 150-350 字，最重要的变化放最前>" },
  "commits": [
    {
      "sha": "<full sha>",
      "comment": "<中文分析，结构化：背景/方法/效果>",
      "sig": "<sig id>",
      "sig_reason": "<一句话归类理由>",
      "tags": ["<type>", "<risk>", "<module>"],
      "pr_number": <PR number or null>
    }
  ]
}
```

写作风格（所有中文产出都必须遵守，2026-11-11 起生效）：
- 读起来像工程师给同事讲 PR，不是论文摘要。**一句说一件事**：
  一个句子最多两个分句，能用句号断开的不用逗号/分号硬连。
- 主语明确、动词直接；长定语拆成短句，先说事物再交代来历。
- 用自然连接词（「之前」「现在」「不过」「代价是」）；禁止压缩黑话
  （「收口」「口径」「落点」「横切面」「归一」「成环」等），换成直白说法。
- **给足上下文，不假设读者懂 vLLM 内部**：每条讲清「这是什么、之前什么
  问题、现在怎样、为什么值得关注」。内部缩写首次出现要展开或带一句解释
  （如 PP→流水线并行、PCP→prefill 上下文并行、mono→单内核 decode 路径）；
  「解锁」「放宽」「追平」这类动词必须带上宾语和原因，不能只说半截。
- 事实优先：保留 PR 号、性能数字、验证结论、风险点；不堆砌次要精确值，
  不写套话，不复述标题。

Analysis depth — the `comment` field should cover:
- **背景** (Background): What problem or motivation drove this change?
  Draw from the PR description's Purpose/Background section.
- **方法** (Method): How was it implemented? Key design decisions,
  approach, scope/limitations. Draw from the PR description and diff.
- **效果** (Effect): What's the impact? Performance numbers, accuracy
  results, breaking changes, follow-up work. Draw from the PR's Test
  results section.
- Write as a structured paragraph using markdown:
  `**背景**：... **方法**：... **效果**：...`
  每段 1-3 个短句，全文约 100-200 汉字。
- For trivial commits (CI config, test-only, docs), a shorter comment
  covering background + effect in 1-2 sentences is acceptable.
- If no PR description is available (no associated PR), base the analysis
  on the commit message, diff stats, and file paths from the digest.

Rules:
- `sig` must be one of the 9 ids in `scripts/sig_config.py` (SIGS list):
  sig-core / sig-large-scale-serving / sig-model-performance /
  sig-spec-decode / sig-quantization / sig-omni / sig-rl / sig-ci / other.
  Classify by the commit's PRIMARY intent, not just file paths; the
  digest's `sig_hint` is a prior, override it when the title/diff says
  otherwise (e.g. a quant kernel speedup → sig-quantization).
- Every commit in the commits file must appear exactly once.
- `pr_number`: the PR number from the digest's `pr:` field (or null if
  no associated PR). Used by the dashboard to link to the PR.
- tags: type (feature/bugfix/refactor/performance/docs/test/chore/ci) +
  risk (high-risk/medium-risk/low-risk) + optional module tag.
- Analysis text in Chinese. Base comments on the PR description (primary
  source), title + paths + stats from the digest, and the patch in
  `data/vllm/commits/<date>.json` for ambiguous or high-impact commits.
  Never fabricate detail you did not verify.
- `sig_summaries`: only SIGs that have commits that day; 3-5 sentences
  each (~150-350 字), synthesizing key developments (not just listing
  commits). 最重要的 1-2 个变化放最前并带 PR 号，其余按方向一句带过。
- `daily_summary`: 结构化 markdown，总长约 800-1400 字，让读者 30 秒
  抓住当天重点（尤其单日 50+ 条的大日子）。固定三段：
  `**今日概览**：` 2-3 句讲清当天基调（条数、主要方向、风险水平）；
  `**今日重点**：` **按平台 → 模型两层分组**：平台用加粗独占一行
  （`**AMD / ROCm**`、`**NVIDIA**`、`**Intel XPU**`、`**跨平台 / 引擎通用**`，
  按当天重要性排序、无内容的平台不写），平台下每条亮点用
  `- **模型名或主题**：1-2 句`（带 PR 号），模型名如 Kimi K3.1、
  DeepSeek-V4.1；平台无关的引擎/前端工作归「跨平台 / 引擎通用」；
  `**需要关注**：` 1-3 条风险、破坏性变更或证据不足的条目（带 PR 号）。
  禁止把全部提交揉进一个长段落。
- Days with many commits: write the file in batches (Write then
  SearchReplace to append) to stay within output limits.

### Step 6: Validate

```bash
python3 .qoder/skills/vllm-sig-update/scripts/validate_analysis.py --date <date>
```

Fix and re-run until it prints `OK`. Only proceed when all dates pass.

### Step 7: Update indexes + refresh dashboard

```bash
python3 scripts/update_indexes.py
```

If the dev server is not already running, start it in background:
`python3 scripts/serve.py --no-open` (default port 8765), then tell the
user to refresh the page. Report a per-SIG count summary of what was
added.

### Step 8: Optional publish

Only if the project is a git repo with a GitHub remote AND the user wants
it published: commit `data/` and push (Pages redeploys automatically).
Ask before pushing.

## Edge cases

- "No new commits found" at Step 2 → nothing new upstream; still run
  Step 4, since older pending dates may exist.
- Anchor missing from meta.json → Step 2 only initializes the anchor
  without fetching history; inform the user, next run will fetch.
- User names a specific date ("更新 7 月 25 日") → after Step 2, restrict
  Steps 4–6 to that date.
