# XIntelOps — Cloud Agent Instructions

This repo runs as a **Cursor Cloud Agent automation**. The agent IS the LLM — no OpenAI or Anthropic API calls in production.

**Mode:** Operator Decision Support (vNext). The email recipient is Hamza (the operator), not the public.

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

### Required fields (vNext)

- `ranked_signals` — all verified signals, force-ranked with scores and one `recommended_action` each
- `operator_decisions` — `one_signal_to_post`, `one_signal_to_watch`, `one_signal_everyone_missing`
- Scores per signal: `edge`, `post_worthiness`, `forecast_value`, `niche_relevance` (1–10)
- `why_hamza_should_care` — operator rationale, not news summary
- Content drafts only for `X POST`, `X THREAD`, or `LINKEDIN` actions
- `journalist.target_post_url` — specific post link (not profile)
- `source_citations` — URLs for top ranked signals

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
- Optimize for decision quality, not collection volume
- Operator should finish reading the email in under 3 minutes
- If ingestion returns empty bundle, report failure; do not fabricate signals

## Reference files

| File | Role |
|---|---|
| `data/xintel_sources.csv` | OSINT/news sources |
| `data/journalists.csv` | 47-analyst engagement roster |
| `prompts/cursor_scan.md` | Operator scoring prompt + JSON schema |
| `docs/POSTING_CADENCE.md` | When to post from the brief |
| `docs/CURSOR_AUTOMATION.md` | Scheduled automation setup |
