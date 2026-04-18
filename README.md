# Massi-Bot — Single-Agent Chatbot for Creator Platforms

Automated 24/7 chatbot for Fanvue and OnlyFans creator accounts. **One Opus 4.7 call per fan message**, with Grok as an uncensor tool the agent calls when its own output isn't explicit enough.

This is the system that runs a full fan relationship — from the first "hey" through climax and back to aftercare — without a human ever touching the keyboard. Built, tested, and battle-hardened against real subscribers on live Fanvue + OnlyFans accounts.

---

## Table of Contents

1. [What This Bot Actually Does](#what-this-bot-actually-does)
2. [Revenue Architecture](#revenue-architecture)
3. [Why Single-Agent, Not Multi-Agent](#why-single-agent-not-multi-agent)
4. [The 10 V2 Upgrades That Power It](#the-10-v2-upgrades-that-power-it)
5. [Prerequisites](#prerequisites)
6. [Quick Start (Fresh Install)](#quick-start-fresh-install)
7. [Testing the System](#testing-the-system)
8. [Content Upload](#content-upload)
9. [Tier Modes](#tier-modes)
10. [Upgrading From the Old Multi-Agent System](#upgrading-from-the-old-multi-agent-system)
11. [Troubleshooting](#troubleshooting)
12. [Project Layout](#project-layout)
13. [License](#license)

---

## What This Bot Actually Does

### The fan's experience, end-to-end

1. **Fan subscribes → GFE mode.** Bot builds genuine rapport. Asks about his life, shares about hers, flirts naturally. No selling. Feels like texting a real girl who's actually into him.

2. **Fan shows interest in seeing more → money-readiness check.** Bot doesn't just route to selling — she explicitly asks if he's willing to spend money. *"real talk — this isn't free... you good with that?"* Fan must say yes before anything sexual costs a dollar. Decline → warm pivot back to chatting, zero pressure.

3. **Fan consents → 6-tier selling pipeline activates.** Bot becomes the DOMINANT partner running a sexual scene through chat. She gives commands (*"pull your cock out and stroke it slowly"*), narrates POV scenes (*"imagine me on my knees..."*), expresses her own arousal (*"I'm so wet right now"*), and controls his orgasm across 6 escalating tiers.

4. **Edge control (tiers 3–5).** She keeps him close to climax but **NEVER** lets him finish. *"Don't you dare cum yet."* *"You cum when I tell you to."* This is the sales mechanism — if he cums at tier 4, he loses interest in tiers 5 and 6. The edge keeps him buying.

5. **Climax permission (tier 6 only).** *"Now baby... cum for me. Give me everything."* Both finish together. Full aftercare follows — she checks if he came, expresses how intense it was.

6. **Post-session → back to GFE.** Consent resets. She's his girlfriend again. They chat about golf, coding, life. The continuation paywall fires after 25–35 messages of non-purchase chatting ($20 gate, jittered). When he gets horny again on a future visit, the cycle repeats with Session 2 content.

### What the bot handles automatically

- **Custom orders** (*"can you do a video in a schoolgirl outfit"*) — detects the request, calls the pricing tool, quotes the price from your WILLS_AND_WONTS.md, takes payment via a custom PPV unlock, fires a 2-click Telegram admin alert for you to confirm/deny.
- **Goodbye / return patterns** — learns how each fan departs and returns. The 50th time he says "brb" feels different than the first.
- **Adaptive settle window** — waits for burst messages to finish before replying, so it never responds to sentence 1 of a 3-sentence message.
- **PPV realness jitter** — Cobalt-Strike-style randomized delays (108–252s) between the heads-up message and the actual PPV drop, so nothing feels automated.
- **6-hour unpaid PPV auto-delete sweep** — unpurchased pitches disappear from chat, so returning fans get a fresh experience.
- **Permanent anti-repetition memory** — across the entire lifetime of the relationship, she never uses the same phrasing twice for high-value moments (money-readiness asks, consent pivots, post-purchase reactions).

---

## Revenue Architecture

| Tier | Default Price | Content |
|------|--------------|---------|
| 1 | $27.38 | Clothed body tease |
| 2 | $36.56 | Lingerie / top tease |
| 3 | $77.35 | Topless |
| 4 | $92.46 | Bottoms off (pussy hidden) |
| 5 | $127.45 | Fully nude, self-play |
| 6 | $200.00 | Climax with toy |
| Continuation | $20.00 | GFE paywall every 25–35 non-purchase messages (never NSFW) |
| Custom | $47–$177+ | Specific requests outside the tier ladder |

**Full session = $561.20.** You can edit tier prices during setup — Claude Code will ask if you want to keep defaults or customize. Odd cents are intentional: they make the pricing look personally set, not corporate-generated.

---

## Why Single-Agent, Not Multi-Agent

Every conversational AI that works at scale (Character.AI, Replika, ChatGPT, Claude.ai, Inflection Pi) is single-model. The reason is simple: multi-agent pipelines fragment context. Each agent sees a narrow slice; no single agent has the full picture; signal gets lost at every handoff.

We built the multi-agent version first (5–7 agents per turn), ran it in production, and documented the failure modes in detail. Then we rebuilt as a single agent with tools. The quality jump was dramatic and the cost dropped ~5–8×. This is the convergent answer the industry arrived at independently — we just took the long way there.

### The pipeline per fan message

```
webhook arrives
  → adaptive settle window (8s initial, +5s per new msg, 30s cap)
  → per-subscriber lock (burst messages merged into one text block)
  → context build (memories, relationship state, time gap, weather, session arc)
  → ONE OPUS 4.7 CALL with tool access
       tools:
         • uncensor(text, tier)           — Grok intensifies when the agent self-censors
         • classify_custom_request(text)  — returns type + price, auto-creates payment tracking
         • fire_custom_payment_alert      — Telegram admin alert for manual payment verification
         • get_specific_memories(query)   — RAG memory lookup
  → code-level post-processing:
       • 8 parallel guardrails (Cresta pattern — zero added latency)
       • PPV heads-up injection + Cobalt-Strike jitter (108–252s)
       • state advancement, HV anti-repeat registry, bandit outcome recording
       • memory extraction
  → execute actions (send messages + PPVs to platform)
  → post-send queue drain
```

**Architecture principle**: *"Code enforces invariants. LLMs handle judgment. One brain, many tools."* Every deterministic rule (pricing, tier ordering, emoji limits, no-redrop, settle timing) lives in code. Every creative/judgment call (what to say, when to push, how to sext, when to use a tool) lives in the single LLM. The two layers never overlap.

---

## The 10 V2 Upgrades That Power It

These are the advanced features that make the bot dramatically better than a stock LLM chatbot. They are all enabled by default — you inherit all of them when you run Massi-Bot.

### 1. RAG Memory System (pgvector + BGE-M3 + Ebbinghaus forgetting)

**What it does:** The bot remembers everything the fan has ever told her — across sessions, across days, across weeks. *"You mentioned you're from Colorado."* *"How did that golf tournament go?"* *"You said you were stressed about work."*

**How it works:**
- Every fan message runs through LLM extraction (`llm/memory_extractor.py`) — pulls facts: job, location, hobbies, emotions, relationships, preferences
- Facts stored as 1024-dimensional BAAI/bge-m3 vector embeddings in Supabase pgvector
- Semantic search retrieves the most relevant memories per turn
- Composite scoring: 35% recency + 30% importance + 35% semantic relevance
- **Ebbinghaus forgetting curve**: memories retrieved often become more stable (slower decay). Unused memories gradually fade — just like human memory.

**Why it matters:** A basic chatbot forgets between messages. This bot builds a cumulative relationship model. After 50 messages she knows his job, his city, his hobbies, his relationship status, his emotional triggers — and uses them naturally in conversation.

### 2. Prompt Caching (90% Token Discount)

**What it does:** The static part of the system prompt (persona, rules, tier guides — ~2500 tokens) is cached by Anthropic's infrastructure. Only the ~500-token dynamic part (subscriber state, memories, history) is re-processed each turn.

**How it works:**
- System prompt split at `# SUBSCRIBER CONTEXT` marker
- Static portion wrapped with `cache_control: {"type": "ephemeral"}`
- First request: 1.25× cost (cache write). All subsequent: 0.1× cost (cache read).
- Cache TTL: 5 minutes (covers rapid-fire conversation turns)

**Why it matters:** 90% discount on the bulk of every call. This is the single biggest cost lever in the system.

### 3. Contextual Bandit (Thompson Sampling, silent observation)

**What it does:** Silently records every bot message + the outcome (fan responded = success) to the `template_rewards` table. Currently in observation-only mode — collecting data without influencing the bot.

**How it works:**
- After every bot message: record message + context (tier, avatar, time of day, subscriber type)
- On next fan message: record "success" via `bandit_recorder.py`
- Thompson Sampling with Beta distributions learns which approaches drive engagement

**Why it matters:** Once 500+ sessions accumulate, the bandit can advise the bot: *"vulnerable register at tier 3 converts 2.3× better than commanding register for first-time buyers."* Data-driven prompt optimization instead of guesswork. Collection is happening from day one.

### 4. High-Value Utterance Registry (15 categories, permanent)

**What it does:** Prevents the bot from repeating critical phrasings across the entire lifetime of the relationship with a fan. Not the last 20 messages — **forever**, per subscriber, per category.

**Categories tracked:** money_readiness_ask, ppv_heads_up, consent_ask, post_purchase_reaction, scene_leadership, sexual_escalation_bridge, goodbye_response, return_acknowledgment, rapport_check_in, custom_pitch, continuation_pitch, and more.

**How it works:**
- Every inflection-point message appended to the appropriate category
- 30-entry FIFO cap per category (older entries go to an archive with hash + timestamp)
- Before each generation, the system prompt gets an anti-repeat block: *"Here's every money-readiness question you've EVER asked this fan — don't echo any of them."*

**Why it matters:** A basic chatbot's anti-repeat window is ~20 messages. This bot's is permanent per category. A fan who's been asked the money-readiness question 15 times over 6 months will never hear the same phrasing twice.

### 5. Adaptive Settle Window

**What it does:** Waits for the fan to finish typing before the bot starts generating. Prevents the *"you dodged my question"* race condition where the bot responds to message 1 before seeing messages 2 and 3.

**How it works:**
- 8-second initial wait after the first message
- +5 seconds per new message that arrives during the wait
- 30-second hard cap
- Settle runs INSIDE the per-subscriber lock (prevents race conditions)
- Up to 2 pre-send regeneration passes if new messages arrive during the LLM call
- Post-send queue drain for messages that arrive during action execution

**Why it matters:** Real creators don't respond to the first sentence of a paragraph. They wait until the fan stops typing, then respond to the whole thought. This makes the bot behave the same way.

### 6. Cobalt-Strike Jitter (Anti-Pattern Detection)

**What it does:** Randomizes timing so the bot never feels deterministic. Named after the penetration testing framework's C2 beacon jitter.

**Applied to:**
- PPV delay: 108–252 seconds between the heads-up message and the actual PPV drop (never exactly 3 minutes)
- Messages-before-first-PPV: randomized 8–14 per subscriber (never always 10)
- Continuation paywall: jittered 25–35 messages, re-randomized after each payment
- All thresholds set once per subscriber or per cycle, not recalculated

**Why it matters:** Deterministic patterns are the #1 way fans detect bots. *"She always drops a PPV at exactly message 10"* → busted. Jitter makes every subscriber's experience slightly different.

### 7. Parallel Guardrails (Cresta Pattern — Zero Added Latency)

**What it does:** 8 safety checks run **concurrently** after the bot generates its response via `asyncio.gather`. Total wall-clock time for all 8 checks = the time of the slowest single one.

**The 8 guardrails:**
1. Text filters (em-dash, system terms, dollar amounts, platform names, AI vocab, reasoning dumps)
2. Tier boundary (explicit language at wrong tiers)
3. No-redrop (pending PPV exists)
4. Persona voice (feminine endearments toward male fans)
5. Other fans mention
6. Fake exclusivity claims
7. Passive voice at high tiers (asking fan to lead instead of commanding)
8. Emoji density (max 1 per message, avg 0.75 across response)

**Why it matters:** The old multi-agent system ran checks serially — each added latency. Parallel execution means all 8 checks run in the same wall-clock time as one. Pattern lifted from Cresta (Fortune 500 contact center AI).

### 8. 6-Hour PPV Auto-Delete Sweep

**What it does:** Automatically deletes unpaid PPVs from the fan's chat after 6 hours via the platform's DELETE APIs. Cleans up stale pitches so returning fans get a fresh experience.

**Why it matters:** A fan who ignored a $92 PPV on Tuesday shouldn't still see it cluttering the chat on Friday. Deletion creates a clean slate — when they return, the bot can pitch again with fresh energy.

### 9. Custom Order System With Admin Verification

**What it does:** Handles specific content requests ("video of you in a golf outfit") outside the tier ladder. Quotes a price from your WILLS_AND_WONTS.md, sends a payment PPV at that price, fires a Telegram alert to the admin with 2-click Confirm/Deny buttons when the fan pays.

**Flow:** Fan requests → bot calls `classify_custom_request` tool → bot quotes price → fan unlocks payment PPV → purchase webhook detects the custom amount → Telegram alert → admin clicks Confirm → bot tells fan *"delivered within 48 hours."*

**Safety built in:**
- Custom payments route as `content_type="custom"` (never advances `ppv_count` or the tier ladder)
- Caption filter is relaxed for customs (so *"strings, oiled tits, fingers deep"* in a custom caption isn't rejected)
- Admin alert shows fan identity (display name, @handle, sub ID prefix, platform) so you can verify on the platform
- Video length capped at 1–2 minutes in the agent's rules (never promises 5+ minute videos)

**Why it matters:** Most chatbots can't handle "I want something specific." They either ignore the request or break the selling flow. This system routes customs through a verified payment flow with human-in-the-loop confirmation — no refund disputes, no angry fans, no runaway expectations.

### 10. Goodbye / Return Pattern Learning

**What it does:** Tracks every departure and return — when he left, whether a PPV was pending, when he came back, whether he opened the PPV on return. Uses this history to adjust farewell tone and push intensity across the relationship.

**Scaling:**
- 0 prior departures: Standard warm farewell + light PPV push
- 1–2 departures: Teasing familiarity (*"again?? lol"*)
- 3+ with high PPV-open rate: Accepting, no push (*"I know you'll be back"*)
- 3+ with low open rate: Light teasing, don't chase

**Why it matters:** Real relationships evolve. The 50th time a fan says "brb" should feel different than the first time. This makes it feel real.

---

## Prerequisites

| Account | Purpose | Cost |
|---------|---------|------|
| Google Cloud Platform | VM hosting | ~$25/mo (e2-medium) |
| Supabase | Database + pgvector RAG | Free tier |
| OpenRouter | Opus 4.7 + Grok | $50 credits to start |
| Claude Pro/Max | To run Claude Code | $20+/mo |
| Telegram | Admin bot | Free |
| Domain name | SSL + webhooks | ~$10/yr |
| Fanvue Developer Account | OAuth + webhooks | Free |
| OnlyFansAPI.com | OF API access | Their pricing |
| Sentry | Error tracking | Free (optional) |

Total first-month cost: ~$40–60.

**About OpenRouter credits:** One Opus 4.7 call per fan message. Typical burn is ~$0.008–0.015 per message. $50 covers thousands of messages. Watch `https://openrouter.ai/activity` for usage — top up before you hit zero or the bot goes silent.

---

## Quick Start (Fresh Install)

### 1. Create a GCP VM

- [console.cloud.google.com](https://console.cloud.google.com)
- Compute Engine → VM Instances → Create Instance
- Machine type: `e2-medium` (2 vCPU, 4 GB RAM)
- Boot disk: Ubuntu 22.04 LTS, 30 GB SSD
- Firewall: Allow HTTP + HTTPS
- Add a firewall rule for TCP 80,443 from `0.0.0.0/0`

### 2. Install Claude Code

SSH into the VM, then:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install -g @anthropic-ai/claude-code

export ANTHROPIC_API_KEY="sk-ant-your-key-here"
echo 'export ANTHROPIC_API_KEY="sk-ant-your-key-here"' >> ~/.bashrc
```

### 3. Clone and Launch

```bash
git clone https://github.com/ChefAir/massi-bot.git
cd massi-bot
claude --dangerously-skip-permissions
```

Claude Code reads `CLAUDE.md` and will:

1. Ask which platform(s) you're using (Fanvue, OnlyFans, both)
2. Ask about your NSFW capability (full tiers 1–6, tiers 1–3 only, or GFE-only)
3. Show you the default tier prices and ask if you want to keep or change them
4. Ask you for your model's hard limits, soft limits, and custom pricing — writes a complete `models/{name}/WILLS_AND_WONTS.md`
5. Walk you through each account and credential one at a time
6. Paste each of the 10 Supabase migrations into the SQL Editor, one at a time, so if one fails you know which
7. Install Docker, nginx, SSL
8. Build + start containers
9. Register webhooks
10. Guide you through content upload and ingestion
11. Walk you through testing with a spare account (see below)

**You don't need to know how to code.** Claude Code handles everything.

---

## Testing the System

Before pointing real subscribers at it:

1. **Open a spare account** on Fanvue or OnlyFans (not your model's account).
2. **Send yourself a free subscription link** from the model's account to the spare.
3. **Chat with the bot** from the spare. It'll respond in 15–30 seconds.
4. **When a PPV arrives, do NOT buy it.** Instead, tell Claude Code: **"simulate PPV purchase for tier 1"**. Claude fires the purchase webhook against your local instance, which advances state exactly as a real purchase would — the bot reacts, then queues the next tier's drop.
5. **Keep Claude Code running** during testing. Real purchases work through the actual webhook; simulated ones need Claude to fire them.

See the "Step 7: Testing" section of `CLAUDE.md` for full details.

---

## Content Upload

On your Fanvue/OnlyFans platform, create these folders:

```
tier1session1/    3–4 images + 1–2 videos (clothed body tease)
tier2session1/    3–4 images + 1–2 videos (lingerie / top tease)
tier3session1/    3–4 images + 1–2 videos (topless)
tier4session1/    3–4 images + 1–2 videos (bottoms off, pussy hidden)  [Full tiers only]
tier5session1/    3–4 images + 1–2 videos (fully nude, self-play)       [Full tiers only]
tier6session1/    3–4 images + 1–2 videos (climax with toy)             [Full tiers only]
continuation/     ~20 images (NEVER NSFW — clothed lifestyle)
```

### Critical content rules

1. **Each tier within a session must look like one continuous moment** — same background, hair, outfit progression. Simulates real-time undressing. If the background changes between tiers, the illusion breaks.
2. **Continuation content is NEVER NSFW** — clothed, casual, lifestyle. This is the $20 GFE paywall content. Nudity here breaks the scarcity model.
3. **Never show skin or nudity for free anywhere.** Not on Instagram, not on the subscriber wall. Scarcity is what makes $27–$200 per tier work.

### Register content

After uploading, tell Claude Code: *"I've uploaded my tier content. Please register it."*

Claude runs `setup/ingest_content.py` to pull media IDs and write them to the `content_catalog` table.

---

## Tier Modes

### Full Pipeline (tiers 1–6)

Explicit NSFW content including masturbation (tier 5) and climax with toy (tier 6). Maximum revenue per session: **$561.20**.

### Tease Only (tiers 1–3)

Clothed → lingerie → topless but no explicit content. Set `active_tier_count: 3` in the model profile. Revenue per session: **~$141**.

### GFE-Only Mode

You cannot (or don't want to) produce NSFW content. Selling pipeline bypassed entirely. Revenue: $20 every 25–35 messages via continuation paywall. Only the `continuation/` folder is needed. Low per-subscriber revenue but still monetizes every relationship.

---

## Upgrading From the Old Multi-Agent System

**Read this section if you are already running the old multi-agent version of Massi-Bot** (the 7-agent pipeline with `conversation_director`, `emotion_analyzer`, `sales_strategist`, `quality_validator`, `gfe_agent`). If you're doing a fresh install, skip to [Quick Start](#quick-start-fresh-install).

### Should you upgrade? Honest answer.

The creator of this system has fully tested the new single-agent version in live production and found it to be **10× better qualitatively** (conversation feel, voice consistency, contextual awareness) and **~5–8× cheaper per message**. But your setup is not identical to his. You should use your own judgment — run the new system in parallel with a feature flag, validate with a handful of test fans, and only cut over globally when you're confident.

Below is a brutally honest side-by-side comparison so you can decide with full information.

### Old multi-agent vs new single-agent — by the numbers

| Dimension | Old (multi-agent) | New (single-agent) |
|---|---|---|
| LLM calls per fan message | 5–7 | 1 (+ occasional tool call) |
| Latency per turn | 15–40 seconds | 8–15 seconds |
| **Cost per fan message** | **~$0.04–0.08** (sometimes higher on regen) | **~$0.008–0.015** |
| Cost per full 6-tier session | ~$2.50–5.00 | ~$0.50–1.00 |
| At 10k messages/month | **~$400–800/mo in LLM fees** | **~$80–150/mo in LLM fees** |
| Context visibility | Fragmented (each agent sees a slice) | Full (one agent sees everything) |
| Voice consistency | Two voices (GFE agent vs Director) — fan experiences a personality shift | One voice always |
| Reasoning-dump leaks | Frequent (700-line Director prompt) | Rare (clean prompt + code filters) |
| Inter-agent coherence failures | Common (Move Advisor says "vulnerable," Voice Stylist writes "commanding") | N/A — one agent |
| Instruction following | Variable (rules buried in long prompts) | Strong (Opus 4.7 + focused prompt + code enforcement) |
| Anti-repeat window | ~20 messages | Permanent per category, per fan |
| Memory retrieval | Context-agnostic | Semantic + recency + importance composite |

### The critical guarantee: **we will not touch or delete your existing files**

When you run Claude Code in your existing repo to start the migration, **Claude will never delete any of your files.** Never. Not one. The migration is designed so your current multi-agent system keeps running in production the entire time the new single-agent system is being wired up alongside it. If you follow the migration flow below, here is what happens:

- Claude **reads** your existing files to understand your setup
- Claude **copies** your existing `agents/orchestrator.py` to `agents/orchestrator_multi_agent.py` as a backup — the original stays untouched
- Claude **adds new files** alongside the existing ones (`agents/single_agent.py`, `agents/parallel_guardrails.py`, `engine/text_filters.py`, `engine/high_value_memory.py`, `engine/custom_orders.py`, `engine/bandit_recorder.py`, `connector/ppv_cleanup.py`)
- Claude **adds a feature-flag switch** (`USE_SINGLE_AGENT` environment variable) that routes to the new agent when `true` and the old agent when `false`
- Default is `USE_SINGLE_AGENT=false`. With the flag off, **your production traffic continues to go through the multi-agent system exactly as it does today — zero behavioral change.**
- You flip the switch to `true` only when you're ready. On a single test fan first. Then broadly. On your schedule.
- If you ever want to roll back: set `USE_SINGLE_AGENT=false` and restart. Done.
- Old multi-agent files **stay on disk indefinitely** unless **you** decide to delete them after you're confident.

**Your fan messages, memories, subscribers, spending history, and transactions do not need to be exported or re-imported.** The new system reads from the same Supabase tables the old system wrote to. The moment you flip the switch, the new agent already knows everything about every fan — because all the relationship data lives in Supabase, and both versions share the same schema.

### The migration flow

In your existing repo on your VM, run:

```bash
cd ~/massi-bot      # or wherever your repo lives
claude --dangerously-skip-permissions
```

Tell Claude: **"I want to upgrade to the single-agent system. Read through my entire project and propose a migration plan. Do NOT modify, move, or delete any of my existing files in this scan — read-only."**

Claude will:

1. **Scan your repo read-only** — no writes, no edits, no deletes.
2. **Check which Supabase migrations you've applied** — most existing users are still on the v1.0 schema and have not run 001–008.
3. **Write a `docs/migration_plan.md`** describing exactly which files it will add, which it will copy for backup, and which it will need to edit (typically just `agents/orchestrator.py` — to add the feature-flag router). You approve the plan before any file is modified.
4. **Apply the plan only after your approval.**
5. **Walk you through the Supabase migrations** (see next section — they're required).
6. **Re-embed your existing RAG memories** to the new vector dimensions (see "Embedding dimension change" below).
7. **Leave `USE_SINGLE_AGENT=false` as the default** so nothing changes in production until you say so.

### Required Supabase migrations (existing users have NOT run these)

The single-agent system depends on schema additions that most existing users haven't applied. These are **safe to run before flipping the switch** — they only add columns and tables; nothing is dropped, renamed, or destructive. The old multi-agent code will ignore the new columns.

In order:

```
migrations/001_model_profile_columns.sql
migrations/002_of_media_id.sql
migrations/003_memory_context_upgrade.sql
migrations/004_system_audit_fixes.sql
migrations/005_memory_cleanup_and_index.sql
migrations/006_ebbinghaus_forgetting.sql
migrations/006_high_value_utterances.sql
migrations/007_template_rewards.sql
migrations/008_bge_m3_embeddings.sql
```

Claude pastes each one into your Supabase SQL Editor one at a time. If any fails with `relation already exists`, that's fine — you've already run that one; skip and continue.

### Embedding dimension change (important)

Migration 008 switches the embedding model from the older MiniLM (384-dim) to BAAI/bge-m3 (1024-dim). This is a massive retrieval-quality upgrade but it means your existing memories are encoded at the wrong dimension for the new model.

**What this means practically:** until you re-embed, the single agent's memory retrieval queries will silently return nothing — the vectors don't match. Your fan memories are not lost; they just need to be re-encoded.

Fix: after applying migration 008, run:

```bash
python3 setup/reembed_memories.py
```

This reads every existing memory in `subscriber_memory` and `persona_memory`, re-encodes it with BGE-M3, and updates the embedding column. It processes in batches with a progress bar. Expect 5–15 minutes depending on how many memories you've accumulated. **Your message content, conversation history, fan state, and spending history are not touched — only the vector embeddings are regenerated.**

**Do this before flipping `USE_SINGLE_AGENT=true`**, or the new agent will feel amnesiac for the first conversation with each fan.

### Your customizations are preserved

If you've customized:
- Your avatar personas in `engine/avatars.py`
- Your per-model `WILLS_AND_WONTS.md` files
- Your `.env` configuration
- Your Supabase content catalog

...**all of it carries over.** The single agent reads the same avatar configs, the same WILLS_AND_WONTS files, the same env vars, and the same content catalog. Nothing needs to be re-done.

### The step-by-step testing plan

Once Claude has added the new files and you've run the migrations + re-embed:

1. **Keep `USE_SINGLE_AGENT=false` in production.** Nothing changes. Multi-agent keeps running.
2. **Spin up a test subscriber** on a spare Fanvue/OnlyFans account (as described in [Testing the System](#testing-the-system)).
3. **Set `USE_SINGLE_AGENT=true` only for your test subscriber** — either via a whitelist env var or by running a second instance just for the test fan.
4. **Chat with the test fan for a while.** Go through consent, a couple tiers, a continuation paywall, maybe a custom request. Use your judgment — does it feel better than the multi-agent version? Are the responses in-character? Is the cost lower in your OpenRouter dashboard?
5. **When confident, flip `USE_SINGLE_AGENT=true` globally.** Restart containers. The new agent is now handling all fan traffic.
6. **Monitor `/stats` and OpenRouter burn rate for 24–48 hours.** If anything looks wrong, flip back to `false` and restart. Zero drama rollback.
7. **Delete the old multi-agent files only when you're 100% sure you don't need them.** Or never. They sit in `agents/orchestrator_multi_agent.py` + the other old agent files costing you nothing.

### Why this matters enough to do it

Three reasons, in order of importance:

1. **Conversation quality.** The single agent reasons holistically about every turn, the same way Claude does in a normal conversation. No signal fragmentation, no voice mismatches, no reasoning dumps leaking into fan-facing messages. Fans stay immersed.
2. **Cost.** 5–8× reduction in LLM fees per message. At 10k messages/month that's hundreds of dollars a month saved. The money you keep.
3. **Latency.** 8–15s per turn vs 15–40s. Fans perceive a bot that types quickly as more human than a bot that takes 30+ seconds.

The creator has said publicly: "It works 10× better than the old version for me." That is a personal testimonial, not a universal guarantee — run it in parallel, validate with your own fans, and migrate on your schedule.

---

## Troubleshooting

**Docker containers won't start**
```bash
docker compose logs --tail=50
```

**Webhooks failing**
```bash
bash setup/test_webhooks.sh
# Expected: HTTP 401/403 (HMAC rejecting unsigned requests = good)
# HTTP 502/504: containers not running
# Connection refused: nginx or SSL misconfigured
```

**Fanvue OAuth fails**
- Redirect URI must EXACTLY match `https://{DOMAIN}/oauth/callback`
- All scopes must be enabled in the Fanvue dashboard
- `curl -I https://{DOMAIN}/health/fanvue` should return 200

**Telegram bot not responding**
```bash
docker compose logs admin_bot --tail=20
```
Check `TELEGRAM_BOT_TOKEN` and that `TELEGRAM_ADMIN_IDS` contains your numeric user ID.

**LLM errors**
```bash
docker compose logs fanvue --tail=50 | grep -i "openrouter\|error"
```
Check OpenRouter credits at `https://openrouter.ai/activity`.

**Bot won't send PPVs**
- Send `/readiness` on Telegram — all tiers must show content
- Send `/resume` on Telegram — engine must be unpaused
- Check connector logs for HMAC errors

**Bot memory queries return nothing (existing users post-migration)**
- Did you run `setup/reembed_memories.py` after migration 008?
- Old MiniLM embeddings (384-dim) don't match BGE-M3 (1024-dim)

---

## Project Layout

```
massi-bot/
├── CLAUDE.md                  Claude Code deployment + migration orchestrator
├── README.md                  This file
├── .env.template              Environment variable template
├── docker-compose.yml         Service orchestration
├── Dockerfile.*               Container build files
├── requirements.txt           Python dependencies
│
├── engine/                    Subscriber model, avatars, onboarding, state
│   ├── models.py                  Subscriber dataclass
│   ├── text_filters.py            Deterministic invariant enforcement
│   ├── high_value_memory.py       Anti-repetition registry (15 categories)
│   ├── custom_orders.py           Custom request detection + state machine
│   ├── bandit_recorder.py         Silent outcome capture (Thompson Sampling prep)
│   └── ...
│
├── agents/                    Single-agent system
│   ├── single_agent.py            One Opus 4.7 call per message + tools
│   ├── orchestrator.py            Thin wrapper called by connectors
│   ├── context_builder.py         Pre-LLM context assembly (pure code)
│   ├── parallel_guardrails.py     8 concurrent safety classifiers
│   ├── uncensor_agent.py          Grok (tool called by single agent)
│   └── media_reactor.py           Media-specific reactions
│
├── connector/                 Platform I/O
│   ├── fanvue_connector.py        FastAPI app, Fanvue webhooks, OAuth
│   ├── of_connector.py            FastAPI app, OF webhooks
│   ├── ppv_cleanup.py             6-hour auto-delete sweep for unpaid PPVs
│   └── ...
│
├── llm/                       LLM + memory infrastructure
│   ├── memory_store.py            pgvector RAG
│   ├── memory_manager.py          Memory orchestration
│   ├── memory_extractor.py        Fact extraction
│   ├── prompt_cache.py            Anthropic prompt caching (90% discount)
│   └── context_awareness.py       Weather + time of day
│
├── persistence/               Supabase CRUD
├── admin_bot/                 Telegram admin commands (/stats, /pause, etc.)
├── migrations/                10 SQL migrations — paste one at a time
├── setup/                     Helper scripts (schema deploy, ingest, webhook test, re-embed)
├── tests/                     pytest suite
└── docs/                      Setup log + design notes (session-scoped)
```

---

## License

MIT. See [LICENSE](LICENSE). Full commercial rights to use, modify, and distribute.
