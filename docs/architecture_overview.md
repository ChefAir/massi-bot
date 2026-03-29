# Massi-Bot Chatbot — Architecture Overview

## System Flow

```
                    Internet
                       │
            ┌──────────┴──────────┐
            │    Nginx (SSL)      │
            │   ports 80 / 443    │
            └──────────┬──────────┘
                       │
          ┌────────────┼────────────┐
          ▼                         ▼
   ┌─────────────┐          ┌─────────────┐
   │   Fanvue    │          │  OnlyFans   │
   │  Connector  │          │  Connector  │
   │  port 8000  │          │  port 8001  │
   │  (FastAPI)  │          │  (FastAPI)  │
   └──────┬──────┘          └──────┬──────┘
          │                        │
          └───────────┬────────────┘
                      ▼
            ┌───────────────────┐
            │   Orchestrator    │
            │  (7-Agent Pipeline)│
            └────────┬──────────┘
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
  ┌─────────┐  ┌──────────┐  ┌─────────┐
  │ Engine  │  │   LLM    │  │ Supabase│
  │ (State  │  │(OpenRouter│  │ (DB +   │
  │ Machine)│  │  + RAG)  │  │pgvector)│
  └─────────┘  └──────────┘  └─────────┘
       │
  ┌────┴────┐
  │  Redis  │
  │ (Tokens │
  │  Cache) │
  └─────────┘
```

## Components

### Connectors (FastAPI webhooks)
- **Fanvue Connector** (port 8000): OAuth 2.0 PKCE, 6 webhook handlers, HMAC-SHA256 signature verification with replay protection
- **OnlyFans Connector** (port 8001): Static API key auth, unified webhook endpoint, HMAC-SHA256 verification
- Both connectors load subscribers from Supabase, run them through the orchestrator, execute resulting BotActions with delays

### Engine (16-State Conversation Machine)
The core state machine that tracks every subscriber's journey:

```
NEW → WELCOME_SENT → QUALIFYING → CLASSIFIED → WARMING → TENSION_BUILD
  → FIRST_PPV_READY → FIRST_PPV_SENT → LOOPING → POST_SESSION
  → RETENTION → RE_ENGAGEMENT → COOLED_OFF → DISQUALIFIED

Special states: GFE_ACTIVE (girlfriend experience), CUSTOM_PITCH
```

Key subsystems:
- **10 Avatar Personas**: girl_boss, housewife, southern_belle, crypto_babe, sports_girl, innocent, patriot, divorced_mom, luxury_baddie, poker_girl (+ goth_domme as avatar #11)
- **120 Scripted Arcs**: 12 scripts per avatar, 16 steps each
- **6-Tier Pricing**: $27.38 → $36.56 → $77.35 → $92.46 → $127.45 → $200.00 (total: $561.20/session)
- **Whale Scoring**: 0-100 score based on demographics, spending, and engagement signals
- **3-No Rule**: Escalating ego bruises on price objections before 5-day cooling period

### Agent Pipeline (7 Agents)
When a message arrives, it flows through this pipeline:

```
1. Context Builder (code, no LLM)     — Builds subscriber profile + memory context
2. Emotion Analyzer (Opus, parallel)   — Scores emotion, engagement, buy readiness
3. Sales Strategist (Opus, parallel)   — Decides: qualify, warm, drop PPV, handle objection
4. Conversation Director (Opus)        — Generates actual response text
5. Uncensor Agent (Grok)               — Makes implied text explicit per tier boundaries
6. Quality Validator (Opus)            — 17-check quality gate (1 retry if fails)
7. BotAction Builder (code)            — Converts to platform-specific send actions
```

**GFE Path**: New subscribers without consent go to the GFE Agent instead of the selling pipeline. It builds genuine rapport, monitors engagement metrics, and asks for sext consent when the moment is right.

**Cost**: ~$0.008 per message (~$0.08-0.12 per full session)

### RAG Memory System
Long-term subscriber memory using pgvector embeddings:

- **Extraction**: Every 5 messages, facts are extracted from fan messages (job, location, relationship, emotions, hobbies, plans)
- **Storage**: Supabase pgvector with all-MiniLM-L6-v2 embeddings (384-dim)
- **Retrieval**: Park et al. composite scoring (0.35 recency + 0.30 importance + 0.35 relevance)
- **Dedup**: Near-duplicates refreshed (sim > 0.78), contradictions superseded (0.60-0.78)
- **Emotional Valence**: Scores -1.0 to +1.0, adjusts bot tone ("be nurturing" vs "match energy")

### Persistence (Supabase)
Four core tables:
- `models` — Creator profiles (stage name, appearance, personality, will-do/won't-do)
- `subscribers` — Fan state (pipeline position, whale score, spending, conversation history)
- `transactions` — Purchase records (PPV, tips, subscriptions)
- `content_catalog` — Content bundles by session/tier with platform media IDs

### Admin Bot (Telegram)
Management interface with commands:
- `/stats` — Subscriber counts, conversion rates, whale percentage
- `/revenue` — Revenue breakdown by transaction type
- `/readiness` — Content catalog completeness per tier
- `/pause` / `/resume` — Engine control
- `/override` — Send manual message to specific subscriber
- Content intake workflow for uploading new bundles

## Pricing Ladder

| Tier | Name | Price | Content Level |
|------|------|-------|---------------|
| 1 | Body Tease | $27.38 | Clothed, fitted outfit, flirty pose |
| 2 | Top Tease | $36.56 | Lingerie, bra peeking, cleavage |
| 3 | Topless | $77.35 | Bare breasts, sensual |
| 4 | Bottoms Off | $92.46 | Full nude, no toys |
| 5 | Self-Play | $127.45 | Fingering, intimate |
| 6 | Climax | $200.00 | Toys, riding, everything shown |
| **Total** | | **$561.20** | Per full session |

**Continuation**: $20.00 every ~30 GFE messages (non-NSFW content only)

## GFE-Only Mode
For creators who cannot produce NSFW content:
- Selling pipeline disabled, GFE Agent handles all conversations
- Revenue comes from $20 continuation paywalls every ~30 messages
- Subs get a genuine girlfriend experience without explicit content
- Can also run tiers 1-4 only (skip 5-6 which require explicit content)

## Key Design Principles

1. **Scarcity drives value**: No skin or nudity shown for free — only in the paid selling pipeline
2. **She leads, never asks**: The bot decides what to send, never asks "what do you want?"
3. **Hesitation sells**: PPV is framed with nervousness ("I'm so nervous to send this..."), not eagerness
4. **3-No escalation**: Price objections get escalating ego challenges, then 5-day cooling
5. **Template selling, LLM conversation**: The selling pipeline (WARMING through POST_SESSION) uses templates only — LLM handles GFE and retention
6. **Response delays are mandatory**: Every BotAction has delay_seconds (30-180) to simulate real typing
7. **Continuation content is NEVER NSFW**: Keeps the paywall pure — explicit content is only in the tier pipeline
