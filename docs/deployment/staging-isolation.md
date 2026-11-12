# Staging isolation: remaining owner steps

Staging runs on the same server as production. To keep a staging mistake from
reaching production data or third-party accounts, staging must use its own
credentials. `deploy-staging.yml` already reads a `STAGING_*` secret for each
shared credential and falls back to the production secret of the same name when
the staging one does not exist. Until the steps below are done, staging still
uses the production credentials.

## Steps, in order

1. **Storage.** In the Backblaze console create a separate bucket for staging
   and an application key restricted to that bucket only (read, write, list,
   delete). Note the key id, the key and the bucket name.
2. **Notion.** In the Notion integrations page create a separate public OAuth
   integration for staging. Set its redirect URI to
   `https://staging.rmirror.io/integrations/notion/callback` (the value the
   workflow already writes to the staging `.env`).
3. **Todoist.** In the Todoist app console create a separate app for staging.
   Set its OAuth redirect URL to
   `https://staging.rmirror.io/integrations/todoist/callback`.
4. **Email.** In the Resend dashboard create a separate API key for staging
   (sending access only, ideally restricted to the staging sending domain).
5. **Google AI.** In Google AI Studio create a separate API key for staging so
   OCR cost and quota are tracked apart from production.
6. **Secrets.** In the GitHub repository settings, add these as secrets of the
   `staging` environment (or repository secrets):

   | Secret name | Contents | Created in |
   |---|---|---|
   | `STAGING_B2_ACCESS_KEY_ID` | key id of the staging-only application key | Backblaze console |
   | `STAGING_B2_SECRET_ACCESS_KEY` | secret of that application key | Backblaze console |
   | `STAGING_B2_BUCKET_NAME` | name of the staging bucket | Backblaze console |
   | `STAGING_GOOGLE_AI_API_KEY` | staging Gemini API key | Google AI Studio |
   | `STAGING_NOTION_CLIENT_ID` | client id of the staging Notion integration | Notion integrations page |
   | `STAGING_NOTION_CLIENT_SECRET` | client secret of that integration | Notion integrations page |
   | `STAGING_TODOIST_CLIENT_ID` | client id of the staging Todoist app | Todoist app console |
   | `STAGING_TODOIST_CLIENT_SECRET` | client secret of that app | Todoist app console |
   | `STAGING_RESEND_API_KEY` | staging Resend API key | Resend dashboard |

   The endpoint and region (`B2_ENDPOINT_URL`, `B2_REGION`) stay shared, since
   they are the same for any bucket in the account. Staging keeps writing under
   the `staging/` key prefix.
7. **Sudoers.** The deploy user's sudo rules are now exact commands without
   wildcards. After this change is merged, log in to the server as root and
   re-run `backend/scripts/setup-deploy-permissions.sh` from the updated
   checkout. Until it is re-run, a command that is not in the old rules prompts
   for a password and the deploy fails. To review the rules without installing
   them, run the script with `--print`.
8. **Deploy and check.** Push to main (or run the staging workflow by hand) and
   confirm the staging health check passes and a test upload lands in the
   staging bucket.
9. **Optional cleanup.** Once the staging secrets exist and staging works,
   remove the `|| secrets.<NAME>` fallbacks from `deploy-staging.yml`, so a
   missing staging secret fails loudly instead of silently using the
   production credential.

## Moving staging to its own VM later

A separate VM would give staging its own database server, disk and deploy user,
so the shared-host risks (a shared sudo user, a shared postgres, resource
exhaustion taking production down) go away. The workflow, the `STAGING_*`
secrets and the sudoers script carry over unchanged apart from the server
secrets and the unit names.
