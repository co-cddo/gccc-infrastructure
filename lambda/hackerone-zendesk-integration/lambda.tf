locals {
  lambda_name = "hackerone-zendesk-integration"
  iam_role    = "lambda-role-h1-zendesk-${terraform.workspace}"
  iam_policy  = "lambda-policy-h1-zendesk-${terraform.workspace}"
}

terraform {
  backend "s3" {
    bucket = "gccc-core-security-tfstate"
    key    = "gccc-infrastructure/hackerone-zendesk-integration.tfstate"
    region = "eu-west-2"
  }
}

variable "staging_iam_role" {
  sensitive = true
  type      = string
}

variable "production_iam_role" {
  sensitive = true
  type      = string
}

provider "aws" {
  region = "eu-west-2"

  assume_role {
    role_arn = terraform.workspace == "production" ? var.production_iam_role : var.staging_iam_role
  }

  default_tags {
    tags = {
      "Service" : "gccc-infrastructure",
      "Reference" : "https://github.com/co-cddo/gccc-infrastructure",
      "Environment" : terraform.workspace
    }
  }
}

resource "aws_iam_role" "lambda_role" {
  name               = local.iam_role
  assume_role_policy = data.aws_iam_policy_document.arpd.json
}

resource "aws_cloudwatch_log_group" "lambda_lg" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = 14
}

resource "aws_iam_policy" "lambda_policy" {
  name        = local.iam_policy
  path        = "/"
  description = "IAM policy for logging from a lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:logs:*:*:*"
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_pa" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

data "aws_iam_policy_document" "arpd" {
  statement {
    sid    = "AllowAwsToAssumeRole"
    effect = "Allow"

    actions = ["sts:AssumeRole"]

    principals {
      type = "Service"

      identifiers = [
        "lambda.amazonaws.com",
      ]
    }
  }
}

resource "aws_lambda_function" "lambda" {
  filename         = "target.zip"
  source_code_hash = filebase64sha256("target.zip")

  function_name = local.lambda_name
  role          = aws_iam_role.lambda_role.arn
  handler       = "main.lambda_handler"
  runtime       = "python3.9"

  memory_size = 256
  timeout     = 30

  lifecycle {
    ignore_changes = [
      environment
    ]
  }
}
