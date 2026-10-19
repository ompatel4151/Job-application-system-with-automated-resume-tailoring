# AWS deployment (Terraform)

**Status: written and validated (`terraform validate`), never applied.** It's
on hold because it costs money; see "Cost" below. Nothing on AWS exists yet,
and Render keeps serving the live backend.

The stack:

- ECR for the image.
- ECS Fargate: 1 task at the smallest size (0.25 vCPU, 0.5 GB).
- An Application Load Balancer, HTTPS only.
- CloudWatch logs, kept for 7 days.
- Secrets Manager for `DATABASE_URL`, `API_KEY`, `GROQ_API_KEY` and
  `REDIS_URL`.
- A GitHub OIDC role, so deploys need no stored AWS keys.

Postgres stays on Supabase. Tasks run in the default VPC with public IPs
instead of behind a NAT gateway, which would cost more than everything else
here combined.

## Cost (estimate, before any apply)

US East (N. Virginia) prices, from the AWS pricing pages on 2026-10-19. The
pages didn't show us-west-1, which is usually somewhat higher. This assumes
the stack runs all month.

| Item | Price | Per month |
|---|---|---|
| Fargate, 0.25 vCPU + 0.5 GB, x86 | $0.000011244 per vCPU-second, $0.000001235 per GB-second | about $9.0 |
| ALB | $0.0225 per hour, plus $0.008 per LCU-hour | about $16.4, plus LCUs (small at this traffic) |
| Public IPv4, about 3 addresses (ALB in 2 zones, plus the task) | $0.005 per hour each (VPC pricing, not re-checked) | about $11 |
| Secrets Manager, 4 secrets | $0.40 each (not re-checked) | about $1.6 |
| CloudWatch logs, ECR storage | per GB | under $1 at this volume |
| **Total** | | **roughly $38 to $44** |

`terraform plan` shows exactly what would be created. Run it and read it
before any apply.

## Ways to avoid paying

- **AWS Free plan.** Accounts created since July 15, 2025 can choose it.
  - A card isn't needed for most sign-ups, the account can't be charged, and
    it comes with $100 (up to $200) in credits for at most 6 months.
  - AWS says Elastic Load Balancing can use the credits. I couldn't confirm
    Fargate from an AWS page, and one third-party guide says Fargate has no
    free tier. Check the Free Tier page in your account's Billing console
    before applying.
  - At roughly $40 a month, $100 covers about 2 months, enough to deploy,
    measure and destroy.
- **The domain for HTTPS.** The GitHub Student Developer Pack includes a free
  domain for the first year (Name.com, Namecheap .me). With it, the ACM
  certificate is free.
- **No domain at all.** CloudFront has an HTTPS `*.cloudfront.net` address
  and a free monthly allowance. The hop from CloudFront to the ALB would
  still need its own protection. Not built here.

## Steps, in order (each needs your approval)

You need: an AWS account, the AWS CLI with `aws configure` done by you, and
Terraform 1.6 or newer. From `infra/`:

1. **Billing alert first, on its own:**

   ```bash
   terraform init
   terraform apply -target=aws_budgets_budget.monthly -var alert_email=you@example.com -var certificate_arn=x -var supabase_url=x
   ```

   AWS Budgets is free for the first two budgets. Confirm the email it sends.
2. **Certificate.** In ACM (in `us-west-1`), request one for a domain you
   control, such as `api.yourdomain`, and validate it by DNS. Put the ARN in
   `terraform.tfvars`, along with `alert_email` and `supabase_url`. The file is
   gitignored.
3. **Plan, read it, then apply:** `terraform plan`, then `terraform apply`.
4. **Secret values,** set from your shell so they never touch the Terraform
   state:

   ```bash
   aws secretsmanager put-secret-value --secret-id job-tracker/DATABASE_URL --secret-string '...'
   ```

   Do the same for `API_KEY`, `GROQ_API_KEY` and `REDIS_URL`.
5. **First image.** In GitHub, set the repository variable
   `AWS_DEPLOY_ROLE_ARN` to `terraform output -raw deploy_role_arn`, then run
   the "Deploy backend to AWS" workflow by hand. Until an image exists, the
   service can't start a task.
6. **Point your domain** (a CNAME) at the ALB's DNS name.
7. **Check it** before moving any traffic:

   ```bash
   curl -s https://api.yourdomain/health
   curl -s -o /dev/null -w '%{http_code}\n' https://api.yourdomain/api/applications
   ```

   The first should return `{"status":"ok"}` and the second `401`.
8. **Cut over.** Set Vercel's `BACKEND_URL` to `https://api.yourdomain` and
   redeploy. To roll back, set it back to the Render URL.

Teardown is in [TEARDOWN.md](../TEARDOWN.md).
