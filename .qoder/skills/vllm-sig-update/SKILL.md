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
  "daily_summary": "<当日整体摘要，中文 3-5 句，提炼主线方向和关键变更>",
  "sig_summaries": { "<sig-id>": "<该 SIG 当日变更重点，中文 2-4 句，提炼背景/方法/效果>" },
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
- `sig_summaries`: only SIGs that have commits that day; 2-4 sentences
  each, synthesizing key developments (not just listing commits).
  Highlight trends, conflicts, and notable impacts.
- `daily_summary`: 3-5 sentences, highlighting the day's main direction,
  key changes, and any risks or follow-ups to watch.
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
