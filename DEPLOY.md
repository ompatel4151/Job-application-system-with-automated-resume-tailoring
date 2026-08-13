# Deploying

The app runs anywhere that can run a Python web process. These instructions use
**Supabase** for Postgres and **Render** for hosting, both on free tiers.

## 1. Database (Supabase)

1. Create a new project at [supabase.com](https://supabase.com). Save the
   database password it generates — it is part of the connection string.
2. Open **Connect** (top of the project dashboard) → **Session pooler**.
3. Copy that connection string. It looks like:

   ```
   postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```

> **Use the Session pooler, not the direct connection.** The direct connection
> (`db.<ref>.supabase.co`) is IPv6-only, and Render's free tier has no IPv6
> egress — it will fail to connect with no useful error.

No SQL to run: the app creates its tables on first startup.

## 2. Hosting (Render)

Either use the blueprint or configure the service by hand.

**Blueprint:** New → Blueprint → point at this repo. Render reads
[`render.yaml`](render.yaml) and creates the service.

**Manual:** New → Web Service → connect this repo, then set:

| Setting | Value |
| --- | --- |
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |

Then add two environment variables under **Environment**:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | the Session pooler string from step 1 |
| `ANTHROPIC_API_KEY` | your key from [platform.claude.com](https://platform.claude.com) |

To run tailoring on Groq's free tier instead, set `GROQ_API_KEY`
(from [console.groq.com/keys](https://console.groq.com/keys)) in place of
`ANTHROPIC_API_KEY`. Either key alone is enough; see the README for the
rate-limit caveat.

Set these in Render's dashboard only — never commit them. `render.yaml` marks
both `sync: false` precisely so they are not stored in the repo.

## 3. Verify

Once the deploy is live:

```bash
curl https://<your-service>.onrender.com/health
```

Expect `{"status":"ok"}`. Then open the root URL for the dashboard and `/docs`
for the OpenAPI reference.

To confirm the database is actually wired up, add a resume through the
dashboard and reload the page — if it persists, Postgres is connected. To
confirm the Claude integration, add an application with a job description and
click **Tailor resume**.

## Notes

- Render's free tier sleeps after inactivity; the first request afterwards takes
  ~30–60s while the instance wakes. The startup retry in `app/main.py` covers a
  database that is still waking up alongside it.
- `postgres://` URLs are rewritten to `postgresql://` automatically, so a URL
  copied from a provider that still uses the old scheme works as-is.
- Connections use `pool_pre_ping` and a 5-minute recycle, so connections the
  pooler has dropped are replaced rather than surfacing as 500s.
