# Teardown

How to remove the deployment so nothing keeps running.

## Rough cost

Standing cost is **$0**, on free plans throughout:

- **Vercel** (frontend) Hobby plan is free for personal projects.
- **Render** (backend) free web services sleep after ~15 minutes of inactivity,
  so the first request after idle takes roughly 50 seconds to wake. They do not
  bill while asleep.
- **Supabase** stays on its free tier (unchanged from Phase 1).
- **LLM tokens** are the only variable cost, billed by Groq/Anthropic per call.

Nothing here can run up a bill, so teardown is about tidiness, not spend.

## Remove the frontend (Vercel)

In the [Vercel dashboard](https://vercel.com/dashboard): open the project >
**Settings** > **Delete Project**.

## Remove the backend (Render)

In the [Render dashboard](https://dashboard.render.com): open
**job-tracker-backend** > **Settings** > **Delete Web Service**.

The old Phase 1 service (**job-application-tracker**, the single Python app) can
be deleted the same way once the new backend is running.

## GitHub and Supabase

- Remove any repository secrets under **Settings > Secrets and variables >
  Actions** if you want them gone. (The test-only CI needs none.)
- The Supabase project is separate. Delete it from the Supabase dashboard if
  you are done with the database. To only empty it, drop the tables; the app
  recreates them on next start.
