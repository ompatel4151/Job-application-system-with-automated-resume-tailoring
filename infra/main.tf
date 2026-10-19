# Backend on AWS: ECR + ECS Fargate behind an ALB, logs in CloudWatch, secrets
# in Secrets Manager. Postgres stays on Supabase. Nothing here has been
# applied; see infra/README.md for the order (billing alert first).
#
# ponytail: local state file, fine for one person applying from one machine.
# Move to an S3 backend before a second person or CI runs terraform apply.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "job-tracker" }
  }
}

variable "region" {
  description = "Same AWS region as the Supabase project, so DB calls stay in-region."
  default     = "us-west-1"
}

variable "alert_email" {
  description = "Where the budget alerts go."
  type        = string
}

variable "monthly_budget_usd" {
  description = "Alert at 50% and 100% of this, actual and forecast."
  default     = 20
}

variable "certificate_arn" {
  description = "ACM certificate for the backend's domain. HTTPS only: without one, tokens would cross the internet in plain text."
  type        = string
}

variable "github_repo" {
  description = "owner/name, allowed to deploy through OIDC."
  default     = "ompatel4151/Job-application-system-with-automated-resume-tailoring"
}

variable "supabase_url" {
  description = "https://<ref>.supabase.co (not a secret)."
  type        = string
}

# ---------- 1. Billing alert: apply this first, on its own ----------

resource "aws_budgets_budget" "monthly" {
  name         = "job-tracker-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = [
      { threshold = 50, type = "ACTUAL" },
      { threshold = 100, type = "ACTUAL" },
      { threshold = 100, type = "FORECASTED" },
    ]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value.threshold
      threshold_type             = "PERCENTAGE"
      notification_type          = notification.value.type
      subscriber_email_addresses = [var.alert_email]
    }
  }
}

# ---------- Network: the default VPC, no NAT gateway ----------
# Tasks get a public IP to reach ECR, Supabase and the LLM APIs directly. A NAT
# gateway would cost more than everything else here combined. Only the ALB can
# reach the tasks.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "alb" {
  name   = "job-tracker-alb"
  vpc_id = data.aws_vpc.default.id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "task" {
  name   = "job-tracker-task"
  vpc_id = data.aws_vpc.default.id
  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ---------- Image, logs, secrets ----------

resource "aws_ecr_repository" "backend" {
  name         = "job-tracker-backend"
  force_delete = true # so terraform destroy can remove it with images inside
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 5 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 5 }
      action       = { type = "expire" }
    }]
  })
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/job-tracker-backend"
  retention_in_days = 7
}

# Terraform creates the empty secrets; their values are set with the AWS CLI
# (infra/README.md), so they never appear in the Terraform state file.
resource "aws_secretsmanager_secret" "app" {
  for_each                = toset(["DATABASE_URL", "API_KEY", "GROQ_API_KEY", "REDIS_URL"])
  name                    = "job-tracker/${each.key}"
  recovery_window_in_days = 0 # destroy deletes immediately, nothing lingers or bills
}

# ---------- ECS ----------

resource "aws_iam_role" "execution" {
  name = "job-tracker-task-execution"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ecs-tasks.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "read_secrets" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "secretsmanager:GetSecretValue"
      Resource = [for s in aws_secretsmanager_secret.app : s.arn]
    }]
  })
}

resource "aws_ecs_cluster" "main" {
  name = "job-tracker"
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "job-tracker-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256 # the smallest Fargate size: 0.25 vCPU
  memory                   = 512 # and 0.5 GB
  execution_role_arn       = aws_iam_role.execution.arn
  container_definitions = jsonencode([{
    name         = "backend"
    image        = "${aws_ecr_repository.backend.repository_url}:latest"
    essential    = true
    portMappings = [{ containerPort = 8080 }]
    environment = [
      { name = "SUPABASE_URL", value = var.supabase_url },
      { name = "LLM_PROVIDER", value = "auto" },
    ]
    secrets = [for name, s in aws_secretsmanager_secret.app : { name = name, valueFrom = s.arn }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.backend.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "backend"
      }
    }
  }])
}

resource "aws_ecs_service" "backend" {
  name            = "job-tracker-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  # Migrations run at startup under a Postgres advisory lock, so a new task
  # starting next to the old one during a deploy is safe.
  health_check_grace_period_seconds = 60

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8080
  }

  # Deploys from GitHub Actions register new task definitions; don't undo them.
  lifecycle {
    ignore_changes = [task_definition]
  }
  depends_on = [aws_lb_listener.https]
}

# ---------- Load balancer, HTTPS only ----------

resource "aws_lb" "backend" {
  name               = "job-tracker"
  load_balancer_type = "application"
  subnets            = data.aws_subnets.default.ids
  security_groups    = [aws_security_group.alb.id]
}

resource "aws_lb_target_group" "backend" {
  name        = "job-tracker-backend"
  port        = 8080
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = data.aws_vpc.default.id
  health_check {
    path    = "/health"
    matcher = "200"
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.backend.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.backend.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# ---------- GitHub Actions deploys with OIDC: no AWS keys stored in GitHub ----------

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

resource "aws_iam_role" "deploy" {
  name = "job-tracker-github-deploy"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Condition = {
        StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
        # Only pushes to main of this repo, not forks or other branches.
        StringLike = { "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:ref:refs/heads/main" }
      }
    }]
  })
}

resource "aws_iam_role_policy" "deploy" {
  role = aws_iam_role.deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = "ecr:GetAuthorizationToken", Resource = "*" },
      {
        Effect = "Allow"
        Action = ["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage"]
        Resource = aws_ecr_repository.backend.arn
      },
      {
        Effect   = "Allow"
        Action   = ["ecs:DescribeTaskDefinition", "ecs:RegisterTaskDefinition", "ecs:DescribeServices", "ecs:UpdateService"]
        Resource = "*"
      },
      { Effect = "Allow", Action = "iam:PassRole", Resource = aws_iam_role.execution.arn },
    ]
  })
}

output "backend_url" {
  value = "https://${aws_lb.backend.dns_name}"
}

output "ecr_repository" {
  value = aws_ecr_repository.backend.repository_url
}

output "deploy_role_arn" {
  value = aws_iam_role.deploy.arn
}
