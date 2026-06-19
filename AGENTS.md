# XIntelOps — Cloud Agent Instructions

This repo runs as a **Cursor Cloud Agent automation**. The agent IS the LLM — no OpenAI or Anthropic API calls in production.

## Standard scan workflow

When triggered (scheduled or manual), execute in order:

```bash
pip install -r requirements.txt
python scripts/run_ingest.py
```

Then read:
- `artifacts/scan_bundle.txt`
- `artifacts/scan_context.json`
- `prompts/cursor_scan.md`

Produce analysis and write JSON to `artifacts/scan_result.json` following the schema in `prompts/cursor_scan.md`.

Required fields for every scan:
- `top_signal.event_date` — when the event happened (within 24h), not scan time
- `source_citations` — at least 2 URLs with names and published dates
- `linkedin_post` — never empty; on Fri/Mon/Wed write full post with `linkedin_today=true`
- `posting_cadence` — when to publish each piece (see docs/POSTING_CADENCE.md)

Then:

```bash
python scripts/finalize_scan.py
```

## One-time seed (first run only)

```bash
python scripts/run_scan.py --seed
```

## Secrets (Cursor Cloud dashboard)

Add in **Cursor → Cloud Agents → Secrets** (not GitHub, not .env):

| Secret | Purpose |
|---|---|
| `SUPABASE_URL` | Database |
| `SUPABASE_SERVICE_ROLE_KEY` | Database writes |
| `RESEND_API_KEY` | Email briefs |
| `RECIPIENT_EMAIL` | Where briefs go |

Do **not** add `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` unless using legacy `LLM_PROVIDER=anthropic` mode.

## Constraints

- Never commit secrets or `.env`
- Never auto-post to X — email brief is human-in-the-loop
- If ingestion returns empty bundle, report failure; do not fabricate signals
- Keep changes scoped to the scan workflow unless explicitly asked

## Reference files

| File | Role |
|---|---|
| `data/xintel_sources.csv` | OSINT/news sources |
| `data/journalists.csv` | 47-analyst engagement roster |
| `prompts/cursor_scan.md` | Full analysis prompt + JSON schema |
| `docs/CURSOR_AUTOMATION.md` | How to create the scheduled automation |
