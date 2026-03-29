# Massi-Bot — AI-Powered Chatbot Engine for Creator Platforms

An automated 24/7 chatting and selling system for Fanvue and OnlyFans. Runs 10 psychological avatar personas off a single model's content, using a 16-state conversation machine, 120 scripted conversation arcs, a 7-agent LLM pipeline, and a 6-tier pricing ladder ($27.38 - $200.00, total $561.20 per session).

---

## What This Does

- Automatically responds to every subscriber message on Fanvue and/or OnlyFans
- Builds genuine rapport through the GFE (Girlfriend Experience) agent before selling
- Guides subscribers through a 6-tier PPV selling pipeline with psychologically optimized scripts
- Remembers subscriber details across conversations using RAG memory (pgvector)
- Sends real-time admin alerts to your Telegram for whale detection, purchases, and errors
- Costs ~$0.008 per message in LLM fees (~$0.08-0.12 per full session)

**Revenue potential**: 100 subscribers x $150 avg spend = **$15,000/month**

---

## How It Works

### The Selling Pipeline
1. New subscriber arrives -> GFE Agent builds genuine rapport (no selling)
2. After rapport metrics are met -> asks for sext consent
3. If consent given -> enters the selling pipeline
4. **Qualifying** -> learns about the subscriber (age, location, interests)
5. **Warming** -> builds sexual tension through flirty conversation
6. **PPV Drops** -> sends tier 1 ($27.38) through tier 6 ($200.00) with bridges between each
7. **Post-Session** -> warm GFE conversation, no selling, relationship maintenance
8. **Retention** -> re-engagement if subscriber goes quiet

### The 7-Agent Pipeline
Every message passes through 7 specialized AI agents:
1. **Context Builder** — Assembles subscriber profile + RAG memories
2. **Emotion Analyzer** — Scores engagement, buy readiness, mood
3. **Sales Strategist** — Decides: qualify, warm, drop PPV, handle objection
4. **Conversation Director** — Generates the actual response text
5. **Uncensor Agent** — Adjusts explicitness to match the current tier
6. **Quality Validator** — 17-check quality gate before sending
7. **BotAction Builder** — Converts to platform API calls with realistic delays

### GFE-Only Mode
If you can't create NSFW content, the system runs in GFE-only mode:
- Subscribers get a genuine girlfriend experience
- Revenue comes from $20 continuation paywalls every ~30 messages
- No tier content needed — just 20 clothed lifestyle photos for continuation

---

## Prerequisites

You need:

| Account | Purpose | Cost |
|---------|---------|------|
| Google Cloud Platform | VM hosting | ~$25/mo (e2-medium) |
| Supabase | Database + RAG memory | Free tier |
| OpenRouter | LLM API calls | $5-20/mo |
| Telegram | Admin bot interface | Free |
| Domain name | SSL + webhook endpoints | ~$10/yr |
| Fanvue Developer Account | OAuth + webhooks | Free (if using Fanvue) |
| OnlyFansAPI.com | OF API access | Varies (if using OnlyFans) |
| Sentry | Error tracking | Free tier (optional) |
| Claude Code | Automated deployment | Requires Anthropic API key |

**Total startup cost**: ~$40-60 for the first month (domain + VM + LLM credits)

---

## Step 1: Create Your Google Cloud VM

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Navigate to **Compute Engine** -> **VM Instances** -> **Create Instance**
4. Configure:
   - **Name**: `massi-bot` (or anything)
   - **Region**: Choose one close to your subscribers
   - **Machine type**: `e2-medium` (2 vCPU, 4 GB RAM)
   - **Boot disk**: Ubuntu 22.04 LTS, 30 GB SSD
   - **Firewall**: Check both "Allow HTTP traffic" and "Allow HTTPS traffic"
5. Click **Create**

### Set Up Firewall Rules

1. Go to **VPC Network** -> **Firewall** -> **Create Firewall Rule**
2. Create a rule:
   - **Name**: `allow-http-https`
   - **Direction**: Ingress
   - **Targets**: All instances in the network
   - **Source IP ranges**: `0.0.0.0/0`
   - **Protocols and ports**: TCP: `80,443`
3. Click **Create**

### SSH Into Your VM

1. Go back to **Compute Engine** -> **VM Instances**
2. Find your instance and click the **SSH** button
3. A browser window will open — click **Authorize** when prompted
4. You're now inside your VM terminal

---

## Step 2: Install Claude Code

Run these commands in your VM terminal:

```bash
# Install Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install Claude Code
sudo npm install -g @anthropic-ai/claude-code

# Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-your-key-here"

# Add to bashrc so it persists
echo 'export ANTHROPIC_API_KEY="sk-ant-your-key-here"' >> ~/.bashrc
```

---

## Step 3: Clone and Deploy

```bash
# Clone the repository
git clone https://github.com/ChefAir/massi-bot.git
cd massi-bot

# Start Claude Code — it will guide you through everything
claude --dangerously-skip-permissions
```

Claude Code reads the `CLAUDE.md` file and automatically:
1. Asks which platform(s) you want to use (Fanvue, OnlyFans, or both)
2. Lists all accounts you need to create with cost estimates
3. Walks you through each credential one at a time
4. Deploys the Supabase database schema
5. Installs Docker, nginx, and SSL certificates
6. Builds and starts all services
7. Guides you through webhook registration
8. Helps with content ingestion

**You don't need to know how to code.** Claude Code handles everything.

---

## Step 4: Session Management (IMPORTANT)

### Exiting a Session
- Press **Ctrl+C twice** to exit Claude Code
- Claude will show a resume command like:
  ```
  claude --resume "abc123-def456-..."
  ```
- **Copy this command immediately**
- Save it to a text file on your LOCAL computer (not the VM)

### Resuming a Session
1. SSH back into your VM (click SSH button on GCP console)
2. Navigate to the project: `cd massi-bot`
3. Paste your resume command and add the permissions flag:
   ```bash
   claude --resume "abc123-def456-..." --dangerously-skip-permissions
   ```

### WARNING: Don't Leave Sessions Idle

**Do NOT leave Claude Code running idle for hours with the VM SSH window open.** The GCP SSH session will eventually disconnect (typically after 30-60 minutes of inactivity), and you will lose access to that Claude Code session.

**Always:**
- Properly exit with Ctrl+C twice when you're done
- Save your resume ID to a local text file
- Resume when you're ready to continue working

---

## Step 5: Content Setup

### Create Content Folders

On your Fanvue/OnlyFans platform, create these folders (vaults/collections):

```
tier1session1/    — 3-4 images + 1-2 videos
tier2session1/    — 3-4 images + 1-2 videos
tier3session1/    — 3-4 images + 1-2 videos
tier4session1/    — 3-4 images + 1-2 videos
tier5session1/    — 3-4 images + 1-2 videos  (skip if GFE-only or T1-T4 mode)
tier6session1/    — 3-4 images + 1-2 videos  (skip if GFE-only or T1-T4 mode)
continuation/     — ~20 images (NEVER NSFW)
```

### What Goes in Each Tier

| Tier | Price | Content | Examples |
|------|-------|---------|----------|
| 1 | $27.38 | **Clothed body tease** | Fitted outfit, flirty pose, showing curves through clothes |
| 2 | $36.56 | **Lingerie / underwear** | Bra peeking, cleavage, lace |
| 3 | $77.35 | **Topless** | Bare breasts, sensual positioning |
| 4 | $92.46 | **Bottoms off** | Full nude, artistic, no toys |
| 5 | $127.45 | **Self-play** | Fingering, intimate touching |
| 6 | $200.00 | **Climax** | Toys, riding, everything shown |
| Cont. | $20.00 | **Clothed lifestyle** | Selfies, GRWM, casual (NEVER NSFW) |

**Total per full session: $561.20**

### Critical Content Rules

1. **Each tier within a session must look like one continuous moment.** Same background, same hairstyle, same outfit progression. The subscriber should believe the model is undressing for them in real time.

2. **Continuation content is NEVER NSFW.** Clothed selfies, lifestyle, mirror shots. This is the GFE paywall content — it's about connection, not nudity.

3. **Never show skin or nudity for free.** Not on Instagram, not on the subscriber wall, not in any free post. The ONLY place subscribers see NSFW content is when they pay for it in the tier pipeline. This scarcity is what allows you to charge $27-$200 per tier.

### After Uploading

Once content is on the platform, tell Claude Code:

> "I've uploaded my content to the tier folders on Fanvue/OnlyFans. Please help me register it in the chatbot system."

Claude Code will use `setup/ingest_content.py` to pull the media IDs and register them in the content catalog.

---

## For Synthetic AI Models / GFE-Only Mode

If you're running a fully synthetic AI character OR cannot create NSFW content:

### Option A: GFE-Only Mode
- Tell Claude Code: "Set up GFE-only mode"
- The selling pipeline is completely disabled
- Subscribers get a genuine girlfriend experience conversation
- Revenue: $20 paywall every ~30 messages
- You only need the `continuation/` folder (20 clothed images)
- Less revenue per subscriber, but still monetizes every conversation

### Option B: Tiers 1-4 Only
- Tell Claude Code: "Set up tiers 1-4 only, skip 5 and 6"
- The system sells through tier 4 (full nude) but stops before explicit content
- Revenue potential: $233.67 per session (tiers 1-4)
- You skip tiers 5-6 which require masturbation/toy content

### Option C: Full Pipeline (Tiers 1-6)
- Requires the ability to create explicit AI-generated images and videos
- Tiers 5-6 involve self-play, toy use, and climax content
- This is a **specialized skill** — don't attempt without experience

> **IMPORTANT**: If you cannot create NSFW AI-generated content, that's perfectly fine. GFE-only mode and tiers 1-4 are both viable business models. Just be honest with Claude Code about your content capabilities during setup.

---

## Making Changes to the System

All modifications are done through Claude Code:

1. SSH into your VM
2. Navigate to the project: `cd massi-bot`
3. Start Claude Code: `claude --dangerously-skip-permissions` (or resume a session)
4. Tell Claude what you want to change

### Best Practices

- **Have Claude analyze ALL project files** at the start of every new session. This gives it full context.
- **Have Claude do web research** for every new idea before implementing it
- **Have Claude create a research doc and implementation manual** under `docs/` BEFORE making any code changes
- This ensures everything is documented, and if your VM disconnects unexpectedly, a new Claude Code session can read the docs and pick up exactly where the last one left off

### Example Requests

- "Modify the pricing to use different tier amounts"
- "Add a new avatar persona for my model's personality"
- "Change the GFE rapport threshold from 15 messages to 25"
- "Add Spanish language support to the bot responses"
- "Show me the conversion rate for each tier"

---

## 1-on-1 Setup Service

Don't want to go through setup yourself? I offer a **5-day hands-on setup** where I'll:

- Configure your entire VM and chatbot system
- Set up all accounts and integrations
- Register your content in the catalog
- Test everything end-to-end
- Train you on monitoring and making changes

By the end of 5 days, you'll have a fully functional chatbot system processing messages 24/7.

### DISCLAIMER

> **This product involves adult content platforms.** The chatbot system automates conversations that may include NSFW content delivery. The 1-on-1 setup covers the **chatbot system only** — I will NOT help create NSFW AI-generated content. That is your responsibility.
>
> **If you cannot create NSFW content**, you can still use GFE-only mode or tiers 1-4. But do NOT purchase the 1-on-1 expecting help with explicit content generation.

**Book your session**: [chattinghelp.massimosintra.com](https://chattinghelp.massimosintra.com)

---

## Troubleshooting

### Docker containers won't start
```bash
docker compose logs --tail=50
# Check for missing env vars or port conflicts
```

### Webhooks not working
```bash
bash setup/test_webhooks.sh
# Should show HTTP 401/403 (signature verification working)
# If HTTP 502/504: containers not running
# If connection refused: nginx not configured or SSL missing
```

### Fanvue OAuth fails
- Verify redirect URI matches EXACTLY: `https://{DOMAIN}/oauth/callback`
- Check that all scopes are enabled in the Fanvue developer dashboard
- Verify SSL certificate is valid: `curl -I https://{DOMAIN}/health/fanvue`

### Bot not responding on Telegram
```bash
docker compose logs admin_bot --tail=20
# Check TELEGRAM_BOT_TOKEN is correct
# Verify TELEGRAM_ADMIN_IDS contains your user ID
```

### LLM responses failing
```bash
docker compose logs fanvue --tail=50 | grep -i "openrouter\|llm\|error"
# Check OPENROUTER_API_KEY has credits remaining
# Visit https://openrouter.ai/activity to see usage
```

### Messages not sending to subscribers
- Check that `content_catalog` has entries: Send `/readiness` to the Telegram bot
- Verify the engine isn't paused: Send `/resume` to the Telegram bot
- Check for HMAC signature errors in connector logs

---

## Project Structure

```
massi-bot/
├── CLAUDE.md              — Claude Code deployment orchestrator
├── README.md              — This file
├── .env.template          — Environment variable template
├── docker-compose.yml     — Docker service orchestration
├── Dockerfile.*           — Container build files
├── requirements.txt       — Python dependencies
│
├── engine/                — Core conversation state machine (16 states, 10 avatars)
├── agents/                — 7-agent LLM pipeline (orchestrator, strategist, director...)
├── connector/             — Platform connectors (Fanvue OAuth, OnlyFans API)
├── persistence/           — Supabase CRUD (subscribers, content catalog, model profiles)
├── llm/                   — LLM client, prompts, guardrails, RAG memory
├── admin_bot/             — Telegram admin bot (stats, revenue, content intake)
│
├── migrations/            — Supabase SQL schema files
├── config/                — Nginx template
├── setup/                 — Deployment helper scripts
├── tests/                 — Test suite (pytest)
└── docs/                  — Architecture and implementation documentation
```

---

## License

MIT License. See [LICENSE](LICENSE) for details. You have full commercial rights to use, modify, and distribute this software.
