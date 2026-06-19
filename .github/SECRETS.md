# GitHub Secrets Setup (Cloud Scheduler)

The XIntelOps pipeline runs automatically via [`.github/workflows/xintelops-scheduler.yml`](workflows/xintelops-scheduler.yml). **No local `.env` file is required for production** — configure secrets in GitHub instead.

## Add secrets

Go to **GitHub repo → Settings → Secrets and variables → Actions → New repository secret**

| Secret | Required | Description |
|---|---|---|
| `SUPABASE_URL` | Yes | `https://<project-ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Service role key (not anon key) |
| `OPENAI_API_KEY` | Yes | Embeddings (`text-embedding-3-small`) |
| `ANTHROPIC_API_KEY` | Yes | Multi-agent chain (Claude Haiku) |
| `RESEND_API_KEY` | Yes | Email delivery |
| `RECIPIENT_EMAIL` | Yes | Where scan briefs are sent |

## One-time setup

1. Apply SQL migrations in `supabase/migrations/` to your Supabase project
2. Add all secrets above
3. Run **Actions → XIntelOps Intelligence Scheduler → Run workflow → mode: `seed`**
4. Run **mode: `scan`** once to verify email delivery

## Schedule

Automatic runs every **3 hours PKT** (8× daily):

| PKT | UTC |
|---|---|
| 00:00 | 19:00 (prev day) |
| 03:00 | 22:00 (prev day) |
| 06:00 | 01:00 |
| 09:00 | 04:00 |
| 12:00 | 07:00 |
| 15:00 | 10:00 |
| 18:00 | 13:00 |
| 21:00 | 16:00 |

## Manual triggers

**Actions → XIntelOps Intelligence Scheduler → Run workflow**

| Mode | Use |
|---|---|
| `scan` | Full pipeline (default scheduled behavior) |
| `ingest-only` | Fetch + vector store only, no LLM/email |
| `seed` | Reload `trusted_sources` + `journalist_engagement_targets` |

## Local development (optional)

For local runs only, copy `.env.example` → `.env`. Production cloud runs use GitHub Secrets exclusively.
