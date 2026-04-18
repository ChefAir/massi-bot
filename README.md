# Massi-Bot — Single-Agent Chatbot for Creator Platforms

Automated 24/7 chatbot for Fanvue and OnlyFans creator accounts. Runs a single Opus 4.7 conversational agent per fan message, with Grok available as an uncensor tool the agent calls when its own output isn't explicit enough.

---

## What This Does

- Responds automatically to every subscriber message on Fanvue and/or OnlyFans
- Builds rapport, asks for consent, and runs a 6-tier PPV pipeline (or tiers 1-3 only, or GFE-only — your choice)
- Remembers fans across conversations via pgvector RAG with an Ebbinghaus forgetting curve
- Handles custom orders (detects specific requests, quotes prices from your WILLS_AND_WONTS.md, fires Telegram admin alerts for payment verification)
- Sends real-time Telegram alerts for whales, purchases, and errors
- LLM cost: one Opus 4.7 call per fan message (~$0.008-0.015), plus occasional Grok tool calls

Default tier pricing (you can change during setup):

| Tier | Price | Content |
|------|-------|---------|
| 1 | $27.38 | Clothed body tease |
| 2 | $36.56 | Lingerie / top tease |
| 3 | $77.35 | Topless |
| 4 | $92.46 | Bottoms off (pussy hidden) |
| 5 | $127.45 | Fully nude, self-play |
| 6 | $200.00 | Climax with toy |
| Cont. | $20.00 | GFE continuation paywall (never NSFW) |

Full session = $561.20.

---

## Architecture: Single Agent, Many Tools

Every fan message goes through one pipeline:

```
webhook arrives
  -> adaptive settle window (8s initial, +5s per new msg, 30s cap)
  -> per-subscriber lock (burst messages merged into one text block)
  -> context build (memories, relationship state, time gap, weather, session arc)
  -> ONE OPUS 4.7 CALL with tool access
         tools: uncensor (Grok), classify_custom, fire_admin_alert, get_memories
  -> code-level post-processing:
         8 parallel guardrails (Cresta pattern — zero added latency)
         PPV heads-up injection + Cobalt-Strike jitter (108-252s)
         state advancement, HV anti-repeat registry, bandit outcome recording
         memory extraction
  -> execute actions (send messages + PPVs to platform)
  -> post-send queue drain
```

**Why single-agent, not multi-agent?** Every conversational AI that works at scale (Character.AI, Replika, ChatGPT, Claude.ai, Inflection Pi) is single-model. Multi-agent pipelines fragment context and degrade conversation quality. Code enforces deterministic invariants; one LLM handles all the judgment.

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

Total startup cost: ~$40-60 for the first month.

**About OpenRouter credits:** One Opus 4.7 call per fan message. Typical burn is ~$0.008-0.015 per message. $50 covers thousands of messages. Watch `https://openrouter.ai/activity` for usage. Top up before you hit zero — otherwise the bot goes silent.

---

## Quick Start

### 1. Create a GCP VM

- Go to [console.cloud.google.com](https://console.cloud.google.com)
- Compute Engine -> VM Instances -> Create Instance
- Machine type: `e2-medium` (2 vCPU, 4 GB RAM)
- Boot disk: Ubuntu 22.04 LTS, 30 GB SSD
- Firewall: Allow HTTP + HTTPS
- Add a firewall rule for TCP 80,443 from `0.0.0.0/0`

### 2. Install Claude Code

SSH into the VM (click the SSH button on GCP console), then:

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

1. Ask which platform(s) you're using
2. Ask about your NSFW capability (full tiers 1-6, tiers 1-3 only, or GFE-only)
3. Show you the default tier prices and ask if you want to keep or change them
4. Ask you for your model's hard limits, soft limits, and custom pricing (writes `WILLS_AND_WONTS.md`)
5. Walk you through each account and credential one at a time
6. Paste each of the 10 database migrations into Supabase one at a time
7. Install Docker, nginx, SSL
8. Build + start containers
9. Register webhooks
10. Guide you through content upload and ingestion
11. Walk you through testing with a spare account

**You don't need to know how to code.** Claude Code handles everything.

---

## Testing the System

Before you point real subscribers at it:

1. **Open a spare account** on Fanvue or OnlyFans (not your model's account).
2. **Send yourself a free subscription link** from the model's account to the spare.
3. **Chat with the bot** from the spare account. It'll respond in 15-30 seconds.
4. **When a PPV arrives, do NOT buy it.** Instead, tell Claude Code: "**simulate PPV purchase for tier 1**". Claude fires the purchase webhook against your local instance, which advances state exactly as a real purchase would — the bot reacts, then queues the next tier's drop.
5. **Keep Claude Code running** during testing. Real purchases work through the actual webhook; simulated ones need Claude to fire them.

See the "Step 7: Testing" section of `CLAUDE.md` for full details.

---

## Session Management

- Press **Ctrl+C twice** to exit Claude Code.
- Claude prints a resume command: `claude --resume "SESSION_ID"`.
- **Save this to a text file on your local machine.**
- To resume: SSH back in, `cd massi-bot`, then:
  ```bash
  claude --resume "SESSION_ID" --dangerously-skip-permissions
  ```

Do not leave Claude Code idle. GCP SSH disconnects after 30-60 minutes of inactivity and you'll lose the session.

---

## Content Upload

On your Fanvue/OnlyFans platform, create these folders:

```
tier1session1/    3-4 images + 1-2 videos (clothed body tease)
tier2session1/    3-4 images + 1-2 videos (lingerie / top tease)
tier3session1/    3-4 images + 1-2 videos (topless)
tier4session1/    3-4 images + 1-2 videos (bottoms off, pussy hidden)  [Full tiers only]
tier5session1/    3-4 images + 1-2 videos (fully nude, self-play)       [Full tiers only]
tier6session1/    3-4 images + 1-2 videos (climax with toy)             [Full tiers only]
continuation/     ~20 images (NEVER NSFW — clothed lifestyle)
```

### Critical Content Rules

1. **Each tier within a session must look like one continuous moment** — same background, hair, outfit progression. It simulates real-time undressing.
2. **Continuation content is NEVER NSFW** — clothed, casual, lifestyle. This is the $20 GFE paywall content.
3. **Never show skin or nudity for free.** Not on Instagram, not on the subscriber wall, not anywhere except behind the paid tier pipeline. Scarcity is what makes $27-$200 per tier work.

### Register Content

After uploading, tell Claude Code: "I've uploaded my tier content. Please register it."

Claude runs `setup/ingest_content.py` to pull media IDs and write them to the `content_catalog` table.

---

## Tier Modes

### Full Pipeline (tiers 1-6)

You can produce explicit NSFW content including masturbation (tier 5) and climax with toy (tier 6). Maximum revenue per session.

### Tease Only (tiers 1-3)

You can do clothed -> lingerie -> topless but no explicit content. Set `active_tier_count: 3` in the model profile. Revenue per session: ~$141.

### GFE-Only Mode

You cannot produce NSFW content at all. Tell Claude Code: "Set up GFE-only mode". The selling pipeline is bypassed entirely. Revenue: $20 every ~30 messages via continuation paywall. Only the `continuation/` folder is needed.

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

---

## Project Layout

```
massi-bot/
├── CLAUDE.md                  Claude Code deployment orchestrator
├── README.md                  This file
├── .env.template              Environment variable template
├── docker-compose.yml         Service orchestration
├── Dockerfile.*               Container build files
├── requirements.txt           Python dependencies
│
├── engine/                    Subscriber model, avatars, onboarding, state
│   ├── models.py                  Subscriber dataclass (+ new fields for single-agent)
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
├── setup/                     Helper scripts (schema deploy, ingest, webhook test)
├── tests/                     pytest suite
└── docs/                      Setup log + design notes (session-scoped)
```

---

## License

MIT. See [LICENSE](LICENSE). Full commercial rights to use, modify, and distribute.
