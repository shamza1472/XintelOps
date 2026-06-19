# XIntelOps

**Intelligence That Acts.**

Production-ready Python pipeline for automated geopolitical intelligence: ingest → vector dedup → multi-agent analysis → human-in-the-loop email.

## Architecture

```
[Data Ingestion] → [Supabase pgvector] → [Multi-Agent AI Chain] → [Resend Email]
```

| Stage | Module | Description |
|---|---|---|
| 1 | `src/xintelops/ingest/` | RSS, HTML, telemetry, journalist fetchers |
| 2 | `src/xintelops/vector/` | OpenAI embeddings + cosine dedup (0.85) |
| 3 | `src/xintelops/agents/` | Verifier → Analyst → Red Team → Strategist |
| 4 | `src/xintelops/delivery/` | HTML brief email via Resend |

## Cloud Setup (Recommended)

Production runs on **GitHub Actions** — no local `.env` required. The cloud scheduler is the main execution path.

### 1. Add GitHub Secrets

See [`.github/SECRETS.md`](.github/SECRETS.md) for the full list. Add these under **Settings → Secrets and variables → Actions**:

- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- `RESEND_API_KEY`, `RECIPIENT_EMAIL`

### 2. Apply database migrations

Run SQL in `supabase/migrations/` against your Supabase project (Dashboard → SQL Editor).

### 3. One-time seed

**Actions → XIntelOps Intelligence Scheduler → Run workflow → mode: `seed`**

### 4. Test a scan

**Actions → XIntelOps Intelligence Scheduler → Run workflow → mode: `scan`**

After that, the scheduler runs automatically every 3 hours PKT (8× daily).

## Local Development (Optional)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in keys for local testing only
python scripts/run_scan.py --seed
python scripts/run_scan.py
```

Ingestion only:

```bash
python scripts/run_scan.py --ingest-only
```

## Data Files

| File | Rows | Purpose |
|---|---|---|
| `data/xintel_sources.csv` | ~158 | OSINT/news source catalog |
| `data/journalists.csv` | 47 | Engagement roster (36 core + 11 expansion) |
| `data/sources.csv` | 10 | CSS selector scraper config |

## Environment Variables

**Production (cloud):** use [GitHub Secrets](.github/SECRETS.md) — the scheduler injects them automatically.

**Local only:** see [`.env.example`](.env.example).

Required keys:

- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY` (embeddings)
- `ANTHROPIC_API_KEY` (agents)
- `RESEND_API_KEY`, `RECIPIENT_EMAIL`

## Scheduling

Automated via [`.github/workflows/xintelops-scheduler.yml`](.github/workflows/xintelops-scheduler.yml):

- **8 runs/day** — every 3 hours PKT (00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00)
- **Manual trigger** — Actions tab → Run workflow (`scan`, `ingest-only`, or `seed`)

## Legacy Compatibility

Set `DUAL_WRITE_LEGACY=true` to continue writing to existing Supabase tables (`raw_signals`, `intelligence_outputs`, `pipeline_log`, etc.) used by the TypeScript edge function.

## Reference

The original production edge function is preserved at [`xintelops-scan-edge-function.ts`](xintelops-scan-edge-function.ts).
