# Teardown

Commands to destroy everything Phase 2 creates, so nothing keeps billing. Set
your values first:

```bash
export PROJECT_ID=your-project-id
export REGION=us-central1
gcloud config set project "$PROJECT_ID"
```

## Rough cost

With the defaults here the standing cost is essentially **$0**:

- **Cloud Run** scales to zero. You pay only for request time; the free tier
  (2M requests, 360k GB-seconds, 180k vCPU-seconds per month) covers a demo.
- **Artifact Registry** stores two small images. Free up to 0.5 GB; beyond that
  about $0.10/GB-month. Pennies.
- **Workload Identity Federation**, the service account, and IAM are free.
- **Supabase** stays on its free tier (unchanged from Phase 1).
- **LLM tokens** are the only variable cost, billed by Groq/Anthropic per call.

The main way to get surprised is leaving `--min-instances` above zero (this
setup does not) or storing many large images. Delete both below.

## Destroy the Cloud Run services

```bash
gcloud run services delete job-tracker-frontend --region "$REGION" --quiet
gcloud run services delete job-tracker-backend  --region "$REGION" --quiet
```

## Delete the container images

```bash
gcloud artifacts repositories delete job-tracker --location "$REGION" --quiet
```

## Remove the deploy identity (Workload Identity Federation + service account)

```bash
gcloud iam workload-identity-pools providers delete github-provider \
  --location=global --workload-identity-pool=github-pool --quiet
gcloud iam workload-identity-pools delete github-pool --location=global --quiet
gcloud iam service-accounts delete \
  gh-deployer@"$PROJECT_ID".iam.gserviceaccount.com --quiet
```

## Optional: the whole project

If the project exists only for this app, deleting it removes everything above
at once (and stops any possible billing):

```bash
gcloud projects delete "$PROJECT_ID"
```

## GitHub and Supabase

- Remove the repository variables and secrets under **Settings > Secrets and
  variables > Actions** if you want them gone.
- The Supabase project is separate. Delete it from the Supabase dashboard if
  you are done with the database.
