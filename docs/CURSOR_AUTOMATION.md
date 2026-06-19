# Cursor Automation Setup (Primary Scheduler)

XIntelOps uses **Cursor Cloud Agent** as the LLM brain — not OpenAI or Anthropic APIs.
This keeps costs inside your Cursor subscription (Cloud Agent usage).

GitHub Actions is **optional** for ingest-only backup. The primary trigger is **Cursor Automation**.

> **Note:** The legacy Supabase edge-function cron (`xintelops-scan`) has been disabled so you only receive emails from this Python + Cursor pipeline — no duplicate briefs.

---

## Architecture

```
Cursor Automation (cron, every 3 hrs PKT)
    ↓
Cloud Agent (YOU — the LLM)
    ↓
1. python scripts/run_ingest.py     ← no LLM APIs, just fetch + hash dedup
2. Read scan_bundle + analyze       ← Cursor model does verification/analysis/red team
3. Write artifacts/scan_result.json
4. python scripts/finalize_scan.py  ← Supabase + Resend email only
```

**Third-party costs in Cursor mode:**
| Service | Required? | Cost |
|---|---|---|
| Cursor Cloud Agent | Yes | Included in Cursor plan (usage-based) |
| Supabase | Yes | Free tier / your existing plan |
| Resend | Yes | Free tier (~100 emails/day) |
| OpenAI | No | Not used |
| Anthropic | No | Not used |
| X API | Optional | Only for accurate journalist reply targeting |

---

## Step 1: Add secrets in Cursor (not GitHub)

Go to **[cursor.com/dashboard](https://cursor.com/dashboard) → Cloud Agents → Secrets**

| Secret | Value |
|---|---|
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key |
| `RESEND_API_KEY` | From resend.com |
| `RECIPIENT_EMAIL` | Your inbox |

Also apply SQL migrations in `supabase/migrations/` to your Supabase project.

---

## Step 2: Create the automation

1. Go to **[cursor.com/automations/new](https://cursor.com/automations/new)**
2. **Name:** `XIntelOps Intelligence Scan`
3. **Repository:** `shamza1472/XintelOps` → branch `main` (after merge)
4. **Trigger:** Scheduled → cron:

   ```
   0 1,4,7,10,13,16,19,22 * * *
   ```

   (Every 3 hours PKT: 00/03/06/09/12/15/18/21)

5. **Prompt** — paste this:

   ```
   Run the XIntelOps intelligence scan workflow. Follow AGENTS.md exactly.

   1. python scripts/run_ingest.py
   2. Read artifacts/scan_bundle.txt, artifacts/scan_context.json, and prompts/cursor_scan.md
   3. Perform the full verify → analyze → red team → content pipeline using your own reasoning (do NOT call OpenAI or Anthropic APIs)
   4. Write valid JSON to artifacts/scan_result.json
   5. python scripts/finalize_scan.py

   If this is the first run and DB catalogs are empty, run python scripts/run_scan.py --seed first.

   Report: session ID, top signal title, crisis flag, email sent status.
   Do not open a PR. Do not auto-post to X.
   ```

6. **Model:** Choose your preferred Cloud Agent model
7. **Tools:** Disable "Create PR" — enable Slack if you want notifications
8. **Save and activate**

---

## Step 3: Test manually

Before waiting for cron, click **Run now** in the automation UI.

Check:
- [ ] `artifacts/scan_bundle.txt` was created
- [ ] `artifacts/scan_result.json` has valid JSON
- [ ] Email arrived in your inbox
- [ ] Supabase `pipeline_log` row created (if dual-write enabled)

---

## Do I need GitHub Actions?

**No** — not for the main pipeline.

| Trigger | Role |
|---|---|
| **Cursor Automation** | Primary — LLM + full scan |
| GitHub Actions (optional) | Ingest-only data collection without LLM |

If you use both, set GitHub workflow to `ingest-only` mode only to avoid duplicate emails.

---

## Legacy mode (external LLM APIs)

Set `LLM_PROVIDER=anthropic` and add `OPENAI_API_KEY` + `ANTHROPIC_API_KEY` if you want the old API-based multi-agent chain via `python scripts/run_scan.py`.

Default is `LLM_PROVIDER=cursor` — no third-party LLM billing.
