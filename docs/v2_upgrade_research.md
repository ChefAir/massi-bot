# Massi-Bot v2.0 Upgrade Research & Implementation Plan

**Date**: 2026-04-05
**Source**: UpgradesApril2026.md (frontier AI upgrade blueprint)
**Goal**: Production-ready upgrades prioritized by cost (free first, then cheap)

---

## Research Summary

The blueprint proposed 9 upgrades. After deep research, here's what's real and what's not worth it for our system:

### Final Priority Ranking

| # | Upgrade | Cost | Effort | Impact | Verdict |
|---|---------|------|--------|--------|---------|
| 1 | **Per-agent model tiering** | FREE | Low (change model strings) | 60-85% cost reduction | DO FIRST |
| 2 | **Ebbinghaus forgetting curve** | FREE | Low (~30 lines + 1 migration) | Better memory decay | DO |
| 3 | **Contextual bandit template selection** | FREE | Low-Med (~100 lines + 1 table) | Learns best templates | DO |
| 4 | **Prompt caching (OpenRouter)** | FREE | Low (~20 lines/agent) | 50-60% input token savings | DO |
| 5 | **BGE-M3 embedding replacement** | FREE | Medium (migration + re-index) | +15-20pt retrieval quality | DO |
| 6 | **DSPy pipeline compilation** | CHEAP (~$15-35/cycle) | Medium (needs eval dataset) | Automated prompt optimization | DO |
| 7 | **EvoPrompt template optimization** | CHEAP ($2-10/cycle) | Medium (needs fitness function) | Evolves better captions/templates | DO |
| 8 | **Semantic caching (Redis)** | FREE | Medium | Only 10-20% hit rate | SKIP |
| 9 | **Mem0/Engram memory** | FREE-CHEAP | Medium | 80% redundant with current system | SKIP |

**Deferred for Future** (too expensive or research-grade for current scale — revisit as volume grows):
- **JEPA behavioral prediction** — Forecast spending intent from conversation patterns. LeJEPA SIGReg makes training feasible. Wait until message volume justifies engineering. (6-10 weeks, GitHub: facebookresearch/jepa)
- **Mamba-3 state tracking** — Complex-valued states for FSM prediction. Mamba4Rec shows sequential user modeling potential. No dialogue benchmarks yet. (GitHub: state-spaces/mamba)
- **Neuro-symbolic sales logic / HCN action masks** — Encode Cialdini principles as verifiable constraints. Our guardrails already handle 80%. Consider when guardrail rejection rate is high. (Ref: XGrammar, Hybrid Code Networks)
- **KTO/RUDDER reinforcement learning** — Revenue-to-training signal without paired preferences. REFUEL eliminates covariate shift. Need 10K+ conversation logs with revenue outcomes first. ($8K+ initial, GitHub: stanfordnlp/dspy)
- **LoRA persona adapters** — 10 persona LoRAs via vLLM S-LoRA. $15-50 total training cost but need self-hosted GPU. Breakeven at ~2100 msgs/day. (GitHub: vllm-project/vllm)

---

## Upgrade 1: Per-Agent Model Tiering (FREE, DO FIRST)

### Current State
All 6 main agents use `anthropic/claude-opus-4-6` ($5/$25 per M tokens). Uncensor uses `x-ai/grok-4.1-fast` ($0.20/$0.50). Total ~$0.008/msg.

### Proposed Tiering

| Agent | Current | Proposed | Input $/M | Output $/M | Why |
|-------|---------|----------|-----------|------------|-----|
| Emotion Analyzer | claude-opus-4-6 | mistral-small-3.1-24b | $0.05 | $0.08 | Simple JSON classification — Opus is 100x overkill |
| Sales Strategist | claude-opus-4-6 | google/gemini-2.5-flash | $0.30 | $2.50 | Needs reasoning but not Opus-level |
| Conversation Director | claude-opus-4-6 | anthropic/claude-haiku-4.5 | $1.00 | $5.00 | Main response gen — Haiku 4.5 is strong enough |
| GFE Agent | claude-opus-4-6 | anthropic/claude-haiku-4.5 | $1.00 | $5.00 | Natural conversation — Haiku handles well |
| Media Reactor | claude-opus-4-6 | mistral-small-3.1-24b | $0.05 | $0.08 | Structured reaction task |
| Quality Validator | claude-opus-4-6 | mistral-small-3.1-24b | $0.05 | $0.08 | Pass/fail — simple structured output |
| Uncensor Agent | grok-4.1-fast | grok-4.1-fast (keep) | $0.20 | $0.50 | Needs uncensored capability |

### Expected Cost
- Current: ~$0.008/msg
- Tiered: ~$0.001-0.002/msg
- **Savings: 75-85%**

### Implementation
Each agent has a `_MODEL` constant or `model=` parameter in its LLM call. Change the string. Same OpenRouter API, same openai client. Files to modify:
- `agents/emotion_analyzer.py`
- `agents/sales_strategist.py`
- `agents/conversation_director.py`
- `agents/gfe_agent.py`
- `agents/media_reactor.py`
- `agents/quality_validator.py`

Also update fallback chains in `llm/llm_client.py`.

**Risk**: Cheaper models may produce lower-quality JSON or miss nuance. Requires testing each agent individually. Keep Opus as fallback if quality degrades.

---

## Upgrade 2: Ebbinghaus Forgetting Curve (FREE)

### Current State
Park et al. scoring: `score = 0.35 * recency + 0.30 * importance + 0.35 * relevance`
Recency is linear decay based on days since creation.

### Proposed Change
Replace linear recency with exponential decay with stability reinforcement:
```
R = e^(-age_days / (base_stability + recall_count))
```
Where `recall_count` increments each time a memory is retrieved and used.

### Implementation
1. Migration: `ALTER TABLE subscriber_memory ADD COLUMN recall_count INT DEFAULT 0`
2. Update SQL RPC `match_subscriber_memory`: replace linear recency term with `exp(-age_days / (1.0 + recall_count))`
3. Update `llm/memory_store.py` `retrieve_memories_with_metadata()`: increment `recall_count` alongside existing `last_accessed` update

~30 lines of code change total.

### Impact
- Frequently-used memories stay strong (mentioned dog's name in 5 conversations = very stable)
- Unused old facts fade faster than linear (reduces retrieval noise)
- Models real human memory more accurately

---

## Upgrade 3: Contextual Bandit Template Selection (FREE)

### Current State
`engine/smart_messaging.py` uses `TimeAwareSelector` + `MessageComposer` with hash-based dedup and time-of-day filtering. Template selection is essentially random within valid time windows.

### Proposed Change
Thompson Sampling bandit that learns which templates perform best per context (state + avatar + time period).

### Implementation
1. New table in Supabase:
```sql
CREATE TABLE template_rewards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_hash TEXT NOT NULL,
    avatar_id TEXT NOT NULL,
    state TEXT NOT NULL,
    time_period TEXT NOT NULL,
    successes INT DEFAULT 0,
    failures INT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_template_rewards_lookup ON template_rewards(avatar_id, state, time_period);
```

2. New file `engine/bandit_selector.py` (~100 lines):
   - `select_template(candidates, avatar_id, state, time_period)` — Thompson Sampling from Beta distributions
   - `record_outcome(template_hash, avatar_id, state, time_period, success)` — update counts

3. Hook into `smart_messaging.py`: after filtering candidates by time, pass through bandit selector instead of random choice.

4. Define "success": subscriber responded within 30 minutes (engagement signal). For PPV templates: subscriber purchased.

### Impact
- Templates that drive engagement get selected more often
- Templates that kill conversations get deprioritized
- Learns per-avatar and per-state preferences automatically
- Improves over time without any manual tuning

---

## Upgrade 4: Prompt Caching on OpenRouter (FREE)

### Current State
Every agent call sends the full system prompt (1000-2000 tokens) fresh each time.

### Proposed Change
Mark static system prompt portions with `cache_control` for Anthropic models on OpenRouter.

### Implementation
For agents using Claude (Director, GFE Agent after tiering):
```python
# Before
messages = [{"role": "system", "content": system_prompt}]

# After
messages = [{"role": "system", "content": [
    {"type": "text", "text": static_persona_rules, "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": dynamic_context}
]}]
```

Split each agent's system prompt into:
- **Static** (persona definition, rules, guardrails) — cached, 90% discount on reads
- **Dynamic** (subscriber context, conversation history, memories) — not cached

### Impact
- Cache writes: 1.25x base cost (first message per 5-min window)
- Cache reads: 0.1x base cost (subsequent messages)
- For a 10-message session: ~50-60% savings on input tokens for cached agents
- Only works for Anthropic models (Director + GFE Agent in proposed tiering)

---

## Upgrade 5: BGE-M3 Embedding Replacement (FREE)

### Current State
`all-MiniLM-L6-v2` (384-dim, 90MB, ~56 MTEB score, 256 max tokens)

### Proposed
`BAAI/bge-m3` (1024-dim, ~570MB fp16, ~70+ MTEB score, 8192 max tokens)

### Implementation
1. Change model name in `llm/memory_store.py`:
```python
_encoder = SentenceTransformer("BAAI/bge-m3")
```
2. Migration SQL:
```sql
ALTER TABLE subscriber_memory ALTER COLUMN embedding TYPE vector(1024);
ALTER TABLE persona_memory ALTER COLUMN embedding TYPE vector(1024);
DROP INDEX IF EXISTS idx_subscriber_memory_embedding;
CREATE INDEX idx_subscriber_memory_embedding ON subscriber_memory 
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```
3. Update RPC function parameter type from `vector(384)` to `vector(1024)`
4. Batch re-embed all existing memories (read each row, encode with new model, update)
5. Update Docker images (adds ~500MB)

### Risks
- CPU inference slower (~200-400ms vs ~20-50ms per embedding). Acceptable for 1-2 embeddings per message.
- Docker image grows 500MB
- Migration requires downtime for re-indexing

### Middle Ground Option
`BAAI/bge-base-en-v1.5` (768-dim, ~440MB) — better than MiniLM, smaller than full M3. But M3 is the real upgrade.

---

## Upgrade 6: DSPy Pipeline Compilation (CHEAP ~$15-35/cycle)

### What It Does
DSPy's MIPROv2 optimizer automatically finds better prompts and few-shot examples for each agent by testing variations against a metric function.

### Implementation
1. `pip install dspy` (add to requirements.txt)
2. Create `optimization/dspy_modules.py` — define each agent as a DSPy module with typed Signature
3. Create `optimization/evaluate.py` — metric function scoring agent outputs against labeled examples
4. Create evaluation dataset from conversation logs (the hard part — need ~50-200 labeled examples per agent)
5. Run optimization: `python optimization/optimize.py --agent emotion_analyzer`
6. Output: optimized prompts saved to `optimization/compiled/`
7. Agents load compiled prompts at startup

### Cost
~$2-5 per agent per optimization cycle via OpenRouter. Full pipeline: $15-35.

### Prerequisites
Need labeled evaluation data. This means going through conversation logs and rating agent outputs as good/bad. Can start with 50 examples per agent.

---

## Upgrade 7: EvoPrompt Template Optimization (CHEAP $2-10/cycle)

### What It Does
Evolutionary algorithm that breeds better PPV captions and conversation templates using LLM as the mutation operator.

### Implementation
1. Create `optimization/evoprompt.py`
2. Initial population: current 720 PPV captions from `engine/avatar_tier_captions.py`
3. Fitness function: response rate from conversation logs (or LLM-as-judge scoring)
4. Each generation: LLM mutates/crosses templates, evaluates against fitness
5. 10 generations x 20 population = 200 LLM calls per cycle
6. Top performers replace weakest templates

### Cost
~$2-10 per optimization cycle at Gemini Flash pricing.

### Prerequisites
Need a fitness function. Can start with LLM-as-judge (Claude Haiku evaluates "would this caption make a subscriber want to unlock the content?") before having real conversion data.

---

## Implementation Order

### Phase 1: Free Upgrades (no money spent)
1. **Per-agent model tiering** — Change 6 model strings. Test each. [1-2 hours]
2. **Ebbinghaus forgetting curve** — 1 migration + ~30 lines. [30 min]
3. **Contextual bandit** — New table + ~100 lines Python. [2-3 hours]
4. **Prompt caching** — Split system prompts, add cache_control. [1-2 hours]

### Phase 2: Free but heavier lift
5. **BGE-M3 embedding swap** — Migration, re-index, Docker rebuild. [half day]

### Phase 3: Cheap optimizations (small API costs)
6. **DSPy compilation** — Build eval dataset, run optimizer. [$15-35 per cycle]
7. **EvoPrompt** — Build fitness function, evolve templates. [$2-10 per cycle]

### Skipped (not worth it at current scale)
- Semantic caching (10-20% hit rate, wrong pattern for contextual chatbot)
- Mem0/Engram (80% redundant with our existing pgvector setup)

### Deferred for Future (revisit as volume grows)
- JEPA behavioral prediction (research-grade, 6-10 weeks, needs custom models)
- Mamba-3 state tracking (no dialogue benchmarks yet, research gap)
- KTO/RUDDER RL ($8K+ upfront, need 10K+ conversation logs)
- LoRA persona adapters (need self-hosted GPU, breakeven at 2100 msgs/day)
- Neuro-symbolic sales logic (our guardrails already handle 80% of this)

---

## Files to Modify

### Phase 1 (model tiering)
- `agents/emotion_analyzer.py` — change model to mistral-small-3.1-24b
- `agents/sales_strategist.py` — change model to gemini-2.5-flash
- `agents/conversation_director.py` — change model to claude-haiku-4.5
- `agents/gfe_agent.py` — change model to claude-haiku-4.5
- `agents/media_reactor.py` — change model to mistral-small-3.1-24b
- `agents/quality_validator.py` — change model to mistral-small-3.1-24b
- `llm/llm_client.py` — update fallback chain with cheaper models
- `llm/validator.py` — change from opus to haiku
- `llm/ppv_readiness.py` — change model if applicable

### Phase 1 (Ebbinghaus)
- `migrations/006_ebbinghaus_forgetting.sql` — new migration
- `llm/memory_store.py` — add recall_count increment on retrieval
- Supabase RPC function update (in migration)

### Phase 1 (contextual bandit)
- `migrations/007_template_rewards.sql` — new table
- `engine/bandit_selector.py` — new file (Thompson Sampling)
- `engine/smart_messaging.py` — hook bandit into template selection

### Phase 1 (prompt caching)
- `agents/conversation_director.py` — split system prompt, add cache_control
- `agents/gfe_agent.py` — same
- `llm/prompts.py` — restructure to separate static vs dynamic portions

### Phase 2 (BGE-M3)
- `migrations/008_bge_m3_embeddings.sql` — alter vector columns + indices
- `llm/memory_store.py` — change model name, update dim references
- `requirements.txt` — model will auto-download on first use
- Batch re-embedding script

### Phase 3 (DSPy + EvoPrompt)
- `optimization/` — new directory with modules, evaluators, runners
- `requirements.txt` — add dspy
