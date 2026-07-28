# Clawbot Workspace — Install

1. **Back up the wizard stubs, then copy these in:**
   ```bash
   cd ~/.openclaw/workspace && mkdir -p _stubs && mv SOUL.md IDENTITY.md USER.md AGENTS.md TOOLS.md MEMORY.md HEARTBEAT.md _stubs/ 2>/dev/null
   cp -R /path/to/clawbot-workspace/* ~/.openclaw/workspace/
   # keep the wizard's identity card (name already matches your BotFather setup):
   cp ~/.openclaw/workspace/_stubs/IDENTITY.md ~/.openclaw/workspace/IDENTITY.md 2>/dev/null
   mkdir -p ~/.openclaw/workspace/desk/mandates ~/.openclaw/workspace/desk/scripts ~/.openclaw/workspace/desk/runs ~/.openclaw/workspace/memory
   ```
   (Leave BOOTSTRAP.md alone if present — it self-deletes after first run.)

2. **Heartbeat config** (cheap ticks, 30m cadence):
   ```bash
   openclaw config set agents.defaults.heartbeat.every 30m
   openclaw config set agents.defaults.heartbeat.model openrouter/anthropic/claude-haiku-4.5
   openclaw config set agents.defaults.heartbeat.isolatedSession true
   openclaw config set agents.defaults.heartbeat.lightContext true
   openclaw config set agents.defaults.compaction.memoryFlush.model openrouter/anthropic/claude-haiku-4.5
   ```
   Note: lightContext loads only HEARTBEAT.md on ticks — which is why HEARTBEAT.md repeats nothing and points at files by path.

3. **Model routing (OpenRouter — set the key's spend cap FIRST):**
   ```bash
   openclaw config set agents.defaults.model.primary openrouter/anthropic/claude-opus-4.7
   openclaw config set agents.defaults.model.secondary openrouter/moonshotai/kimi-k3
   ```
   Per-task tiers (T1–T4) per TOOLS.md — assign models on the scheduled tasks / sub-agents as they're created (`openclaw agents add --model ...`). Verify slugs in the OpenRouter catalog. Enable prompt caching.

4. **Version control:**
   ```bash
   cd ~/.openclaw/workspace && git init && git add -A && git commit -m "clawbot bootstrap v1"
   ```

5. **Smoke test:** restart session, then ask over Telegram: "what's the desk process for a technical-only idea?" (should recite the debate requirement), "what's in the book?" (should read desk/positions.md and say flat/paper), and "buy 100 AAPL" (should refuse — execution boundary).

6. **Backups (required — GitHub is not):** local git covers history; it does not cover `~/.openclaw` config/credentials/sessions. Weekly, via cron or calendar reminder:
   ```bash
   openclaw backup create --output /Volumes/YOUR_SSD/clawbot-backups/ --verify
   ```
   Keep the archive off the Mini (external SSD or personal cloud folder). A private GitHub remote for the workspace is optional off-site versioning, not a backup — if used: private repo, single-repo fine-grained PAT, .gitignore any .env, and decide consciously whether memory/ daily notes belong off-machine.

## Still to build
- `desk/scripts/prices.py` — the yfinance feed (validate end-to-end before anything else)
- `desk/mandates/*.md` — 19 specialist mandate files
- Country ETF list confirmation in `desk/universe.md`
- US market holiday awareness for HEARTBEAT.md (static list in the file is fine)
