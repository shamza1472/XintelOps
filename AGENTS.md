# XIntelOps — Cloud Agent Instructions

This repo runs as a **Cursor Cloud Agent automation**. The agent IS the LLM — no OpenAI or Anthropic API calls in production.

**Mode:** Operator Decision Support. Email recipient is Hamza (the operator).

## Standard scan workflow

```bash
pip install -r requirements.txt
python scripts/run_ingest.py
```

Read `artifacts/scan_bundle.txt`, `artifacts/scan_context.json`, `prompts/cursor_scan.md`.

Write `artifacts/scan_result.json` then:

```bash
python scripts/finalize_scan.py
```

## Required fields

- `ranked_signals` — force-ranked with scores + one `recommended_action` each
- `operator_decisions` — post / watch / everyone_missing
- `source_package` — min 2 URLs with `why_supports` for the post-now recommendation
- `source_citations` — same sources, used in email source block
- Content drafts only for `X POST`, `X THREAD`, or `LINKEDIN` actions
- LinkedIn: always draft on Mon/Wed/Fri (200–350 words) unless crisis-only exception
- Journalist: `target_post_url` (specific post, not profile)

## Queue (handled at finalize)

The pipeline reads the previous `content_schedule` row and resolves:
- carried forward
- replaced by higher-priority signal
- expired and archived

Never output vague “post in 4–6 hours” — `what_most_missed` becomes the tracked later-post.

## Secrets

`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`, `RECIPIENT_EMAIL`

## Reference

| File | Role |
|---|---|
| `prompts/cursor_scan.md` | Operator scoring + JSON schema |
| `docs/POSTING_CADENCE.md` | Posting actions from the brief |
| `docs/CURSOR_AUTOMATION.md` | Scheduler setup |
