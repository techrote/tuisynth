---
corpus: tuisynth
programme: trio
document_id: TRIO-LOCAL
status: authority
---
# Local workflow, LM Studio host and model roster

TRIO is developed entirely inside a local development VM. Agents clone, branch, test, run CI,
review and merge locally; nothing is pushed and no GitHub (or any other) credentials exist in
the VM. Models come from two sources only: **OpenCode free-tier models** (no login) and
**LM Studio** serving local models from the host GPUs.

## Topology

```text
Windows host                                       Linux dev VM (ezvm, QEMU user-mode NAT)
  LM Studio server 127.0.0.1:1234  <── 10.0.2.2:1234 ──  opencode 1.19.x
    TITAN RTX 24 GB (PCIe 3.0 x16)  one model at a time   ~/workspace/tuisynth (anonymous clone)
    V100 16 GB (PCIe 2.0 x4)        disabled for now      python trio/tools/ci.py (local CI)
  orchestrator: Windows CI lane at milestones          OpenCode free tier (internet, no login)
```

- The VM reaches host loopback services at `10.0.2.2`, so LM Studio stays bound to
  `127.0.0.1` and is never exposed on the LAN.
- Clone anonymously: `git clone https://github.com/techrote/tuisynth.git`. After that the VM
  needs the network only for `pip`/`uv` downloads, `npm` packages used by OpenCode, and
  free-tier model calls. Tests never use the network.
- Results leave the VM as a git bundle (`git bundle create trio.bundle --all`) copied to the
  host; a human decides whether to publish.

## LM Studio host settings

| Setting | Value | Why |
|---|---|---|
| Server | `lms server start --port 1234` (bound to 127.0.0.1) | reachable from the VM via NAT only |
| GPU selection | TITAN RTX only; V100 disabled (`disabledGpus` = V100) | the V100's cooling must be reworked before sustained load; its PCIe 2.0 x4 link makes cross-card splits slow |
| Model fit | each model fully on one card (`--gpu max`), no CPU/RAM offload, no tensor split | avoids PCIe-bound layers and keeps the speed predictable |
| Flash attention | on | needed for a quantised KV cache |
| Evaluation batch | 128 tokens | keeps temporary buffers small enough for Qwen's 128k context on the Titan |
| KV cache | `q8_0` for K and V | about half the KV memory of f16 with negligible quality loss |
| JIT loading | on, idle TTL 30 min | models swap automatically on request; only one 24 GB model fits at a time |
| Parallel requests | 1 per loaded model | the issue lanes that use local models run serially |

Re-enabling the V100 later (after its waterblock is reworked) adds a second, independent
model slot: gpt-oss-20b (below) fits entirely inside its 16 GB and can serve reviews while the
Titan serves implementation. Splitting a single model across both cards is not planned.

## Model roster

All quantisations are official or well-known GGUF builds downloaded from Hugging Face. VRAM
and speed were measured on the TITAN RTX with the settings above; "tok/s" is single-stream
generation speed at a short context.

| Role | LM Studio model id | Source / quant | Context | VRAM (measured) | tok/s (measured) |
|---|---|---|---|---|---|
| Titan primary: careful implementer | `qwen3.8-27b` | `unsloth/Qwen3.8-27B-GGUF` UD-Q4_K_XL (17.6 GB) | 131072 | 24194 MiB peak total | 31.1 |
| Titan fast: long-context coder | `kwaipilot_kat-coder-v2.5-dev` | `bartowski/Kwaipilot_KAT-Coder-V2.5-Dev-GGUF` IQ4_XS (18.8 GB) | 131072 (up to 262144, not tested) | 20528 MiB peak total | 104.2 |
| V100 (later): reviewer / small tasks | `gpt-oss-20b` | `ggml-org/gpt-oss-20b-GGUF` MXFP4 (12.1 GB) | 131072 | download only; not loaded | not run yet |

Notes:

- **Qwen3.8-27B** is dense, with a hybrid linear-attention layout: only 16 full-attention
  layers keep a KV cache, so 128k context costs little memory. Use its recommended thinking
  sampling: temperature 1.0, top_p 0.95, top_k 20, min_p 0. It is the default for DSP and
  engine issues where correctness matters more than speed.
- **KAT-Coder-V2.5-Dev** is a 35B-A3B mixture-of-experts coder trained with agentic RL; it is
  several times faster per token and has the more reliable tool calls. Use temperature 0.6,
  top_p 0.95. It is the default for UI, packaging and broad multi-file issues.
- Do **not** use "uncensored", "abliterated" or merged fine-tunes for agent work; their tool
  calling is less reliable.
- Do not run models larger than one card. The previously tested 37.8 GB Q8 build needed both
  GPUs and is not part of the roster.

### Qualification on 2026-10-14

Both Titan models passed three out of three tool-call trials: each returned one `write_file`
call with the exact requested path and file content. Qwen loaded in 10.7 s (warm file cache),
KAT in 19.5 s. The long prompts contained 59268 tokens for Qwen and 59226 for KAT; time to first
token was 186.7 s and 67.0 s respectively. Long-context decode was 28.8 and 71.4 tok/s. Peak
Titan temperature was 38 C for both; V100 memory remained at its 10 MiB baseline throughout.
VRAM figures above are total `nvidia-smi` readings, including the desktop, rather than model
allocation alone. All three GGUF file sizes and SHA-256 hashes matched their public source
manifests. GPT-OSS was not loaded or benchmarked.

Qwen's short and long speed trials exhausted their output limits in reasoning, so those trials
measure decode speed, not a completed code answer. Tool-call trials did complete. Qwen's short
trial also reported automatic MTP draft-token statistics; its speed includes that runtime
behavior. OpenCode's end-to-end READY and file-tool smoke tests are separate gates in the VM.

Do not rely on saved settings alone. The running LM Studio app initially ignored settings
written during an earlier session. Restarting the idle app preserved the GPU configuration
file byte-for-byte; explicit per-load settings then confirmed the Titan selection. Load through
the host SDK with the configuration below before starting the VM agent, and check the returned
load configuration and `nvidia-smi`. This changes only that loaded instance, not global GPU
settings:

```python
config = {
    "gpu": {"ratio": "max", "mainGpu": 1, "splitStrategy": "favorMainGpu", "disabledGpus": [0]},
    "gpuStrictVramCap": False,
    "contextLength": 131072,
    "evalBatchSize": 128,
    "flashAttention": True,
    "offloadKVCacheToGpu": True,
    "llamaKCacheQuantizationType": "q8_0",
    "llamaVCacheQuantizationType": "q8_0",
}
```

The CLI memory estimator substantially overestimated Qwen's quantized-cache requirement. Its
strict VRAM cap silently reduced a 16k load from full offload to 62 layers while the SDK still
reported `ratio: max`; that load was rejected as qualification evidence. The measured results
above used full offload with the cap off. Qwen has little desktop VRAM headroom at 128k: if
current display allocation prevents a full fit, use 65536 context and lower the OpenCode
context limit to match, or use KAT. Never accept partial offload, shared model weights or a
second GPU as a workaround. Keep the V100 disabled.

## OpenCode free-tier models (no login)

Listed by `opencode models opencode` in OpenCode 1.19.0 on 2026-10-14. The roster changes; run
the command again before a session and record the id actually used.

`opencode/big-pickle`, `opencode/exo-free`, `opencode/ling-3.1-flash-free`,
`opencode/longcat-2.5-preview-free`, `opencode/mimo-v2.6-flash-free`,
`opencode/nemotron-3-ultra-free`, `opencode/nemotron-3.5-lightning-free`,
`opencode/step-5-preview-free` (plus niche or contributor-only entries that are not used).

Free-tier endpoints are rate-limited and may log prompts; they receive only this repository's
public code and documents. Never paste secrets into any prompt.

## OpenCode configuration in the VM

`~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "lmstudio": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "LM Studio (host)",
      "options": { "baseURL": "http://10.0.2.2:1234/v1" },
      "models": {
        "qwen3.8-27b": {
          "name": "Qwen3.8 27B (Titan)",
          "limit": { "context": 131072, "output": 32768 },
          "options": { "temperature": 1.0, "topP": 0.95 }
        },
        "kwaipilot_kat-coder-v2.5-dev": {
          "name": "KAT-Coder V2.5 Dev (Titan)",
          "limit": { "context": 131072, "output": 32768 },
          "options": { "temperature": 0.6, "topP": 0.95 }
        }
      }
    }
  }
}
```

Check it from the VM before starting a run:

```sh
curl -s http://10.0.2.2:1234/v1/models | head
opencode models lmstudio
```

top_k and min_p are not sent by OpenCode; set them as the per-model defaults in LM Studio
(My Models -> model -> Inference).

## Per-issue model assignment

The orchestrator assigns one implementer per issue and, for kit and engine issues, an
independent reviewer that is a **different** model (findings go under `## Independent
review` in the review record; see `trio/AGENTS.md` section 5).

| Issues | Implementer | Independent reviewer | Fallback if stuck |
|---|---|---|---|
| 001 foundation + local CI | KAT (Titan) | free tier | Qwen |
| 002, 003, 004 kit params / engine / DSP | Qwen (Titan) | KAT or free tier | free tier |
| 005, 006, 007, 008 kit input / skins / TUI / shell | KAT (Titan) | Qwen or free tier | free tier |
| 009, 011, 013 instrument engines | Qwen (Titan) | free tier | KAT |
| 010, 012, 014 instrument UIs | KAT (Titan) | free tier | Qwen |
| 015, 016 stretch | Qwen (Titan) | KAT | free tier |
| 017 release | KAT (Titan) | free tier | Qwen |

- Only one Titan model is loaded at a time, so independent issues that run in parallel
  (see the programme's "Parallelism") use one Titan lane plus free-tier lanes.
- Each agent records the exact model id in `STATUS.md` and `PROVENANCE.md`
  (`lmstudio/<id>` or `opencode/<id>`).
- After two blocked attempts with one model, retry once with the fallback, then leave the issue
  `blocked` for a human.

## Windows milestone lane (orchestrator, on the host)

After TRIO-008, after each instrument UI and before TRIO-017's tag, the orchestrator copies the
VM's `main` to the host (`git bundle` + `git clone`), runs
`python trio/tools/ci.py --lanes py311,py314` there and records the result in the next review
record. Failures become fix commits on the next issue branch.
