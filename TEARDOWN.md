# Teardown

How to remove the deployment so nothing keeps running.

## Rough cost

Standing cost is **$0**. Both services run on Render's **free** plan:

- Free web services sleep after ~15 minutes of inactivity, so the first request
  after idle takes roughly 50 seconds to wake. They do not bill while asleep.
- **Supabase** stays on its free tier (unchanged from Phase 1).
- **LLM tokens** are the only variable cost, billed by Groq/Anthropic per call.

Free services can't run up a bill, so teardown is about tidiness, not spend.

## Remove the Render services

In the [Render dashboard](https://dashboard.render.com):

1. Open **job-tracker-frontend** > **Settings** > **Delete Web Service**.
2. Do the same for **job-tracker-backend**.
3. If you created them from a Blueprint, delete the Blueprint too
   (**Blueprints** > the blueprint > **Delete**).

The old Phase 1 service (**job-application-tracker**, the single Python app) can
be deleted the same way once the new services are running.

## GitHub and Supabase

- Remove any repository secrets under **Settings > Secrets and variables >
  Actions** if you want them gone. (The test-only CI needs none.)
- The Supabase project is separate. Delete it from the Supabase dashboard if
  you are done with the database. To only empty it, drop the tables; the app
  recreates them on next start.
