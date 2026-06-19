# GitHub Secrets (Optional Ingest Workflow)

The **primary scheduler is Cursor Automation** — see [docs/CURSOR_AUTOMATION.md](../docs/CURSOR_AUTOMATION.md).

GitHub Actions only runs optional **ingest-only** backup (`xintelops-ingest.yml`). It does not call any LLM APIs.

## Secrets for optional ingest workflow

| Secret | Required |
|---|---|
| `SUPABASE_URL` | Yes (if using Supabase storage) |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes (if using Supabase storage) |

## Secrets for Cursor Cloud Agent (primary)

Add these in **Cursor Dashboard → Cloud Agents → Secrets**:

| Secret | Required |
|---|---|
| `SUPABASE_URL` | Yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes |
| `RESEND_API_KEY` | Yes |
| `RECIPIENT_EMAIL` | Yes |

**Not needed in Cursor mode:** `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
