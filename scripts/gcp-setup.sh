#!/usr/bin/env bash
#
# One-time GCP setup for the Cloud Run + GitHub Actions pipeline.
#
# Creates: Artifact Registry repo, a deploy service account with the roles the
# pipeline needs, and keyless Workload Identity Federation trust for this
# GitHub repo. Then prints the GitHub variables/secrets to set.
#
# Prereqs: gcloud installed and logged in (`gcloud auth login`), a GCP project
# with billing enabled, and the GitHub repo in owner/repo form.
#
# Usage:
#   PROJECT_ID=my-proj GITHUB_REPO=ompatel4151/Job-application-system-with-automated-resume-tailoring \
#     bash scripts/gcp-setup.sh
#
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
: "${GITHUB_REPO:?set GITHUB_REPO (owner/repo)}"

REGION="${REGION:-us-central1}"
AR_REPO="${AR_REPO:-job-tracker}"
POOL="github-pool"
PROVIDER="github-provider"
SA_NAME="gh-deployer"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "Project: $PROJECT_ID | Region: $REGION | Repo: $GITHUB_REPO"
gcloud config set project "$PROJECT_ID" >/dev/null

echo "==> Enabling APIs"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com

echo "==> Artifact Registry repo ($AR_REPO)"
gcloud artifacts repositories create "$AR_REPO" \
  --repository-format=docker --location="$REGION" \
  --description="Job tracker images" 2>/dev/null || echo "   (exists)"

echo "==> Deploy service account"
gcloud iam service-accounts create "$SA_NAME" \
  --display-name="GitHub Actions deployer" 2>/dev/null || echo "   (exists)"

echo "==> Granting roles to $SA_EMAIL"
for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" --role="$role" \
    --condition=None >/dev/null
done

echo "==> Workload Identity Federation"
gcloud iam workload-identity-pools create "$POOL" \
  --location=global --display-name="GitHub Actions" 2>/dev/null || echo "   (pool exists)"

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --location=global --workload-identity-pool="$POOL" \
  --display-name="GitHub" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GITHUB_REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com" 2>/dev/null \
  || echo "   (provider exists)"

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
WIF_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}"

echo "==> Letting the repo impersonate the deploy SA"
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${GITHUB_REPO}" \
  >/dev/null

cat <<EOF

Done. Now set these on the GitHub repo (Settings > Secrets and variables > Actions).

Repository VARIABLES:
  GCP_PROJECT_ID = ${PROJECT_ID}
  WIF_PROVIDER   = ${WIF_PROVIDER}
  DEPLOY_SA      = ${SA_EMAIL}
  LLM_PROVIDER   = auto

Repository SECRETS:
  DATABASE_URL       = <your Supabase session pooler URL>
  API_KEY            = <a long random string; also used by the frontend proxy>
  GROQ_API_KEY       = <your Groq key>            # or leave unset
  ANTHROPIC_API_KEY  = <your Anthropic key>       # or leave unset

Or set them with gh:
  gh variable set GCP_PROJECT_ID --body "${PROJECT_ID}"
  gh variable set WIF_PROVIDER --body "${WIF_PROVIDER}"
  gh variable set DEPLOY_SA --body "${SA_EMAIL}"
  gh variable set LLM_PROVIDER --body "auto"
  gh secret set DATABASE_URL
  gh secret set API_KEY
  gh secret set GROQ_API_KEY

Then push to main (or run the Deploy workflow manually) to deploy.
EOF
