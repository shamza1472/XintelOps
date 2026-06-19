# XIntelOps

**Intelligence That Acts.**

Automated geopolitical intelligence pipeline. **Cursor Cloud Agent is the LLM brain** — no OpenAI or Anthropic API costs in production.

```
[Ingest scripts] → [Cursor Agent analysis] → [Supabase + Email brief] → [You post manually on X]
```

## Primary setup: Cursor Automation

**Full guide:** [docs/CURSOR_AUTOMATION.md](docs/CURSOR_AUTOMATION.md)

1. Merge PR and apply `supabase/migrations/` SQL
2. Add secrets in **Cursor Dashboard → Cloud Agents → Secrets**:
   - `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
   - `RESEND_API_KEY`, `RECIPIENT_EMAIL`
3. Create automation at [cursor.com/automations/new](https://cursor.com/automations/new):
   - **Cron:** `0 1,4,7,10,13,16,19,22 * * *` (every 3 hours PKT)
   - **Prompt:** see [docs/CURSOR_AUTOMATION.md](docs/CURSOR_AUTOMATION.md)
4. Click **Run now** to test

The Cloud Agent runs ingest → analyzes with its own model → sends your email brief.

## What costs money

| Service | Cursor mode | Notes |
|---|---|---|
| Cursor Cloud Agent | Your Cursor plan | Includes the LLM — no separate API keys |
| Supabase | Free tier / existing | Storage only |
| Resend | Free tier | Email delivery |
| OpenAI / Anthropic | **Not used** | Set `LLM_PROVIDER=anthropic` only for legacy mode |
| X API | Optional ~$25–50/mo | Accurate journalist reply targeting only |

## Manual workflow (what the agent runs)

```bash
python scripts/run_ingest.py          # fetch sources, hash dedup, write bundle
# agent reads artifacts/scan_bundle.txt + prompts/cursor_scan.md → writes scan_result.json
python scripts/finalize_scan.py       # Supabase + Resend email
```

## Data files

| File | Purpose |
|---|---|
| `data/xintel_sources.csv` | ~158 OSINT/news sources |
| `data/journalists.csv` | 47-analyst engagement roster |
| `prompts/cursor_scan.md` | Analysis prompt + JSON schema |
| `AGENTS.md` | Cloud agent instructions |

## Legacy mode (external LLM APIs)

Set `LLM_PROVIDER=anthropic` and add OpenAI + Anthropic keys to run `python scripts/run_scan.py` with API-based agents.

## Optional: GitHub Actions ingest backup

`.github/workflows/xintelops-ingest.yml` — ingest-only, no LLM, no email. See [.github/SECRETS.md](.github/SECRETS.md).

## Reference

Original TypeScript edge function: [`xintelops-scan-edge-function.ts`](xintelops-scan-edge-function.ts)
