locals {
  lambda_name         = "crawler-govuk-reference-content"
  iam_role            = "lambda-role-crawler-govuk-reference-content-${terraform.workspace}"
  iam_policy          = "lambda-policy-crawler-govuk-reference-content-${terraform.workspace}"
  cron_trigger        = "0 5 ? * MON *"
  s3_processed_bucket = terraform.workspace == "production" ? "gc3-processed-a1205b9b-1e39-4d70" : "gccc-processed-a1205b9b-1e39-4d70"
}

terraform {
  backend "s3" {
    bucket = "gccc-core-security-tfstate"
    key    = "gccc-infrastructure/crawler-govuk-reference-content.tfstate"
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
      "Service" : "crawler-govuk-reference-content",
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
  description = "IAM policy for Lambda"

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
      {
        Action = [
          "s3:PutObject"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:s3:::${local.s3_processed_bucket}/govuk/objects/*"
      },
      {
        Action = [
          "lambda:InvokeFunction"
        ]
        Effect   = "Allow"
        Resource = aws_lambda_function.lambda.arn
      }
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

data "aws_lambda_layer_version" "standard" {
  layer_name = "python311-standard-requirements"
}

data "aws_lambda_layer_version" "pull" {
  layer_name = "python311-pull-requirements"
}

resource "aws_lambda_function" "lambda" {
  filename         = "target.zip"
  source_code_hash = filebase64sha256("target.zip")

  function_name = local.lambda_name
  role          = aws_iam_role.lambda_role.arn
  handler       = "main.lambda_handler"
  runtime       = "python3.11"

  memory_size = 4096
  timeout     = 900

  layers = [
    data.aws_lambda_layer_version.standard.arn,
    data.aws_lambda_layer_version.pull.arn,
  ]

  environment {
    variables = {
      ENVIRONMENT         = terraform.workspace
      S3_PROCESSED_BUCKET = local.s3_processed_bucket
    }
  }
}

resource "aws_cloudwatch_event_rule" "time_trigger" {
  is_enabled          = terraform.workspace == "production"
  name                = "${local.lambda_name}-trigger"
  schedule_expression = "cron(${local.cron_trigger})"
}

resource "aws_cloudwatch_event_target" "check_lambda" {
  rule      = aws_cloudwatch_event_rule.time_trigger.name
  target_id = "${local.lambda_name}-check_lambda"
  arn       = aws_lambda_function.lambda.arn
}

resource "aws_lambda_permission" "allow_cloudwatch_to_call_lambda" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.time_trigger.arn
}
