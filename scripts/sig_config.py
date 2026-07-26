#!/usr/bin/env python3
"""vLLM SIG (Special Interest Group) definitions and path-based triage.

SIG taxonomy follows the latest vLLM community roadmap
([Roadmap] vLLM Roadmap Q3 2026, vllm-project/vllm#48168), where the
project goal is broken down into special interest groups (#32455).

Each commit is assigned exactly one primary SIG. `classify_by_paths`
provides a deterministic heuristic used both as a pre-triage before the
LLM call and as a fallback when the LLM output is missing/invalid.
"""

# Ordered dict: earlier entries win when multiple SIGs match equally.
SIGS = [
    {
        "id": "sig-spec-decode",
        "name": "SIG Spec Decode",
        "description": (
            "Speculative decoding: draft models (EAGLE/MTP/DFlash/DFlare/DSpark), "
            "acceptance-length tuning, dynamic speculation, ngram proposer, "
            "rejection sampler, drafting modes for long context."
        ),
    },
    {
        "id": "sig-quantization",
        "name": "SIG Quantization",
        "description": (
            "Quantization: FP8 / NVFP4 / INT2-4 / GPTQ / AWQ, quantized KV cache "
            "and KV compression, QuantConfig / QuantKey dispatch, quant fusion "
            "(RMSNorm+quant, activation+quant, etc.), llm-compressor / ModelOpt integration."
        ),
    },
    {
        "id": "sig-large-scale-serving",
        "name": "SIG Large Scale Serving",
        "description": (
            "Large-scale serving: prefill-decode disaggregation, distributed / "
            "multi-tier KV cache offloading (KV connector, Mooncake, LMCache), "
            "KV events, expert parallelism (wide EP / elastic EP / EPLB), context "
            "parallelism, data parallelism, multi-node routing and scheduling."
        ),
    },
    {
        "id": "sig-omni",
        "name": "vLLM-Omni",
        "description": (
            "Multimodal and omni models: vision / audio / video inputs, real-time "
            "full-duplex interaction models, streaming video generation, "
            "multimodal processors and embeddings."
        ),
    },
    {
        "id": "sig-rl",
        "name": "RL Ecosystem",
        "description": (
            "Reinforcement-learning ecosystem support: weight update / weight sync "
            "APIs, sleep & wake_up mode, collective_rpc, rollout integration with "
            "RL frameworks (vime, Prime-RL, Nemo-RL, verl, OpenRLHF)."
        ),
    },
    {
        "id": "sig-model-performance",
        "name": "SIG Model Performance",
        "description": (
            "Model performance: CUDA / Triton kernels, attention backend "
            "optimization, fused MoE kernels, torch.compile and CUDA graph "
            "optimization, per-model performance sprints, accuracy & performance "
            "regression benchmarking."
        ),
    },
    {
        "id": "sig-ci",
        "name": "SIG CI",
        "description": (
            "Continuous integration: Buildkite / GitHub Actions pipelines, test "
            "infra, flaky test quarantine, multi-node CI, build system, docker "
            "images, release engineering."
        ),
    },
    {
        "id": "sig-core",
        "name": "SIG Core",
        "description": (
            "Core engine: scheduler, KV cache manager, model runner, Flat Model "
            "migration, engine core & executor, API frontend (incl. Rust frontend), "
            "tool calling, structured output, sampler, cold start time, model "
            "loading, config system, new model architecture support."
        ),
    },
    {
        "id": "other",
        "name": "Other",
        "description": "Docs, chores, and changes not owned by a specific SIG.",
    },
]

SIG_IDS = [s["id"] for s in SIGS]
SIG_BY_ID = {s["id"]: s for s in SIGS}


def sig_name(sig_id):
    s = SIG_BY_ID.get(sig_id)
    return s["name"] if s else sig_id


# ── Path-based heuristics ────────────────────────────────────────────
# (prefix or substring, sig) — checked in order, first match scores.
# A commit's SIG = the SIG with the highest file-match score.

PATH_RULES = [
    # Spec decode
    ("vllm/v1/spec_decode/", "sig-spec-decode"),
    ("vllm/spec_decode/", "sig-spec-decode"),
    ("vllm/config/speculative", "sig-spec-decode"),
    ("vllm/v1/sample/rejection_sampler", "sig-spec-decode"),
    ("eagle", "sig-spec-decode"),
    ("mtp", "sig-spec-decode"),
    # Quantization
    ("vllm/model_executor/layers/quantization/", "sig-quantization"),
    ("vllm/quantization/", "sig-quantization"),
    ("csrc/quantization/", "sig-quantization"),
    ("vllm/config/quant", "sig-quantization"),
    ("quantized_kv", "sig-quantization"),
    ("quant_fusion", "sig-quantization"),
    # Large scale serving
    ("vllm/distributed/kv_transfer/", "sig-large-scale-serving"),
    ("vllm/distributed/kv_events", "sig-large-scale-serving"),
    ("vllm/distributed/eplb/", "sig-large-scale-serving"),
    ("vllm/distributed/", "sig-large-scale-serving"),
    ("vllm/v1/offloading/", "sig-large-scale-serving"),
    ("vllm/v1/kv_offload", "sig-large-scale-serving"),
    ("vllm/v1/core/kv_cache_coordinator", "sig-large-scale-serving"),
    ("disagg", "sig-large-scale-serving"),
    ("mooncake", "sig-large-scale-serving"),
    ("lmcache", "sig-large-scale-serving"),
    ("nixl", "sig-large-scale-serving"),
    ("expert_parallel", "sig-large-scale-serving"),
    ("data_parallel", "sig-large-scale-serving"),
    # Omni / multimodal
    ("vllm/multimodal/", "sig-omni"),
    ("vllm/model_executor/models/vision", "sig-omni"),
    ("vllm/entrypoints/openai/serving_audio", "sig-omni"),
    ("multimodal", "sig-omni"),
    ("omni", "sig-omni"),
    # RL ecosystem
    ("vllm/v1/worker/gpu_worker_rl", "sig-rl"),
    ("rlhf", "sig-rl"),
    ("weight_update", "sig-rl"),
    ("weight_sync", "sig-rl"),
    ("sleep_mode", "sig-rl"),
    ("wake_up", "sig-rl"),
    # Model performance (kernels / compile / benchmarks)
    ("csrc/", "sig-model-performance"),
    ("vllm/kernels/", "sig-model-performance"),
    ("vllm/attention/ops/", "sig-model-performance"),
    ("vllm/v1/attention/backends/", "sig-model-performance"),
    ("vllm/model_executor/layers/fused_moe/", "sig-model-performance"),
    ("vllm/compilation/", "sig-model-performance"),
    ("vllm/triton_utils/", "sig-model-performance"),
    ("benchmarks/", "sig-model-performance"),
    ("cuda_graph", "sig-model-performance"),
    # CI / build
    (".buildkite/", "sig-ci"),
    (".github/", "sig-ci"),
    ("docker/", "sig-ci"),
    ("Dockerfile", "sig-ci"),
    ("requirements/", "sig-ci"),
    ("setup.py", "sig-ci"),
    ("pyproject.toml", "sig-ci"),
    ("CMakeLists.txt", "sig-ci"),
    ("cmake/", "sig-ci"),
    (".pre-commit-config", "sig-ci"),
    ("tools/", "sig-ci"),
    # Core engine
    ("vllm/v1/core/", "sig-core"),
    ("vllm/v1/engine/", "sig-core"),
    ("vllm/v1/executor/", "sig-core"),
    ("vllm/v1/worker/", "sig-core"),
    ("vllm/v1/sample/", "sig-core"),
    ("vllm/v1/structured_output/", "sig-core"),
    ("vllm/engine/", "sig-core"),
    ("vllm/entrypoints/", "sig-core"),
    ("vllm/model_executor/models/", "sig-core"),
    ("vllm/model_executor/model_loader/", "sig-core"),
    ("vllm/model_executor/", "sig-core"),
    ("vllm/config/", "sig-core"),
    ("vllm/config.py", "sig-core"),
    ("vllm/sampling_params", "sig-core"),
    ("vllm/outputs", "sig-core"),
    ("vllm/inputs/", "sig-core"),
    ("vllm/transformers_utils/", "sig-core"),
    ("vllm/lora/", "sig-core"),
    ("vllm/platforms/", "sig-core"),
    ("vllm/attention/", "sig-core"),
    ("rust/", "sig-core"),
    ("vllm/", "sig-core"),
    # Docs & misc
    ("docs/", "other"),
    ("examples/", "other"),
    ("README", "other"),
]

# Message keywords used as a tie-breaker / booster (substring, sig, weight).
MESSAGE_RULES = [
    ("spec decode", "sig-spec-decode"),
    ("speculative", "sig-spec-decode"),
    ("eagle", "sig-spec-decode"),
    ("mtp", "sig-spec-decode"),
    ("draft model", "sig-spec-decode"),
    ("quant", "sig-quantization"),
    ("fp8", "sig-quantization"),
    ("fp4", "sig-quantization"),
    ("gptq", "sig-quantization"),
    ("awq", "sig-quantization"),
    ("disagg", "sig-large-scale-serving"),
    ("kv connector", "sig-large-scale-serving"),
    ("kv offload", "sig-large-scale-serving"),
    ("prefill decode", "sig-large-scale-serving"),
    ("mooncake", "sig-large-scale-serving"),
    ("eplb", "sig-large-scale-serving"),
    ("elastic ep", "sig-large-scale-serving"),
    ("multimodal", "sig-omni"),
    ("[omni]", "sig-omni"),
    ("vision", "sig-omni"),
    ("audio", "sig-omni"),
    ("[rl]", "sig-rl"),
    ("rlhf", "sig-rl"),
    ("sleep mode", "sig-rl"),
    ("weight sync", "sig-rl"),
    ("[kernel]", "sig-model-performance"),
    ("triton", "sig-model-performance"),
    ("cuda graph", "sig-model-performance"),
    ("fused moe", "sig-model-performance"),
    ("[perf]", "sig-model-performance"),
    ("[ci]", "sig-ci"),
    ("[build]", "sig-ci"),
    ("[ci/build]", "sig-ci"),
    ("[doc]", "other"),
    ("[docs]", "other"),
]

# Pure test-only or doc-only commits can skip the LLM SIG call entirely.
AUTO_OTHER_DIRS = ("docs/", "examples/")
AUTO_OTHER_EXTS = (".md", ".rst", ".txt")
AUTO_CI_DIRS = (".buildkite/", ".github/", "docker/", "tests/", "tools/", "requirements/")


def _match_path(filename):
    fn = filename.lower()
    for pattern, sig in PATH_RULES:
        p = pattern.lower()
        if p.endswith("/"):
            if fn.startswith(p) or ("/" + p) in fn:
                return sig
        elif p in fn:
            return sig
    return None


def classify_by_paths(commit):
    """Heuristically assign a SIG from changed file paths + message.

    Returns (sig_id, confidence) where confidence is 'high' when the
    signal is unambiguous, 'low' otherwise (LLM should refine).
    """
    files = commit.get("files", [])
    message = (commit.get("message", "") or "").split("\n")[0].lower()

    scores = {}
    for f in files:
        sig = _match_path(f.get("filename", ""))
        if sig:
            scores[sig] = scores.get(sig, 0) + 1

    for kw, sig in MESSAGE_RULES:
        if kw in message:
            scores[sig] = scores.get(sig, 0) + 2

    if not scores:
        return "other", "low"

    # sig-core from the catch-all "vllm/" rule is weak evidence; prefer
    # any specific SIG that also scored.
    best = max(scores.items(), key=lambda kv: (kv[1], -SIG_IDS.index(kv[0])))
    sig_id, best_score = best
    total = sum(scores.values())
    confidence = "high" if best_score / total >= 0.7 and len(scores) <= 2 else "low"
    return sig_id, confidence


def is_trivial_commit(commit):
    """True when a commit touches only docs/examples/CI/test paths, so its
    SIG can be decided without an LLM call."""
    files = commit.get("files", [])
    if not files:
        return False
    for f in files:
        fn = f.get("filename", "")
        if fn.startswith(AUTO_OTHER_DIRS) or fn.endswith(AUTO_OTHER_EXTS):
            continue
        if fn.startswith(AUTO_CI_DIRS):
            continue
        return False
    return True


def triage_trivial_sig(commit):
    """SIG for a trivial (docs/CI-only) commit."""
    files = commit.get("files", [])
    if any(f.get("filename", "").startswith(AUTO_CI_DIRS) for f in files):
        return "sig-ci"
    return "other"


def build_sig_prompt_section():
    """SIG taxonomy text block injected into the analysis prompt."""
    lines = []
    for s in SIGS:
        lines.append(f"- **{s['id']}** ({s['name']}): {s['description']}")
    return "\n".join(lines)
