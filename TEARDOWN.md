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

## Remove the AWS backend (only if it was ever applied)

This is the only part that bills by the hour. From `infra/`, with the same
variables you applied with:

1. In Vercel, point `BACKEND_URL` back at Render first, so the site keeps
   working.
2. `terraform destroy`. Read the list, then type `yes`. It removes the ECS
   service and cluster, the ALB, the target group, security groups, ECR
   (images included, `force_delete`), the log group, the secrets (immediately,
   no 30-day recovery window), the IAM roles, the OIDC provider and the
   budget.
3. Check that nothing is left that could bill:

   ```bash
   aws ecs list-clusters --region us-west-1
   aws elbv2 describe-load-balancers --region us-west-1 --query 'LoadBalancers[].LoadBalancerName'
   aws ec2 describe-addresses --region us-west-1
   aws secretsmanager list-secrets --region us-west-1 --query 'SecretList[].Name'
   ```

   Each should come back empty, or without any `job-tracker` entries.
4. Delete the ACM certificate and the DNS record by hand; they weren't made by
   Terraform.
5. In GitHub, delete the `AWS_DEPLOY_ROLE_ARN` variable, so the deploy
   workflow is skipped again.

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
