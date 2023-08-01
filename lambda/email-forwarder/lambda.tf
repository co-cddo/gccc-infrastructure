data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "main.py"
  output_path = "lambda.zip"
}

resource "aws_lambda_function" "lambda" {
  provider = aws.eu_west_1

  filename         = "lambda.zip"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  description   = "${terraform.workspace}: Email Forwarding"
  function_name = local.lambda_name
  role          = aws_iam_role.lambda_role.arn
  handler       = "main.lambda_handler"
  runtime       = "python3.10"

  publish = true

  memory_size = 512
  timeout     = 60

  environment {
    variables = {
      Region           = "eu-west-1"
      MailS3Bucket     = "mailbox.${local.email_domain}"
      MailSenderDomain = local.email_domain
    }
  }

  #lifecycle {
  #  ignore_changes = [
  #    last_modified
  #  ]
  #}

  depends_on = [
    aws_iam_role_policy_attachment.lambda_pa,
    aws_cloudwatch_log_group.lambda_lg,
  ]
}

resource "aws_lambda_permission" "with_ses" {
  provider       = aws.eu_west_1
  statement_id   = "AllowExecutionFromSES-${terraform.workspace}"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.lambda.function_name
  principal      = "ses.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
  source_arn     = "arn:aws:ses:eu-west-1:${data.aws_caller_identity.current.account_id}:receipt-rule-set/inbound-${terraform.workspace}:receipt-rule/*"
}

resource "aws_iam_role" "lambda_role" {
  provider           = aws.eu_west_1
  name               = local.iam_role
  assume_role_policy = data.aws_iam_policy_document.arpd.json
}

resource "aws_cloudwatch_log_group" "lambda_lg" {
  provider          = aws.eu_west_1
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = 14
}

# See also the following AWS managed policy: AWSLambdaBasicExecutionRole
resource "aws_iam_policy" "lambda_policy" {
  provider    = aws.eu_west_1
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
      {
        Action = [
          "kms:GetPublicKey",
          "kms:DescribeKey",
          "kms:Decrypt",
          "kms:Verify",
          "kms:Sign"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:kms:*:*:key/*",
      },
      {
        Action = [
          "kms:ListKeys"
        ]
        Effect   = "Allow"
        Resource = "*",
      },
      {
        Action = [
          "s3:Get*",
          "s3:Delete*",
          "s3:List*",
          "s3:Put*"
        ]
        Effect = "Allow"
        Resource = [
          "arn:aws:s3:::mailbox.${local.email_domain}/*",
          "arn:aws:s3:::mailbox.${local.email_domain}",
        ],
      },
      {
        Action = [
          "ses:SendRawEmail"
        ]
        Effect = "Allow"
        Resource = [
          "arn:aws:ses:eu-west-1:${data.aws_caller_identity.current.account_id}:identity/*",
        ],
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_pa" {
  provider   = aws.eu_west_1
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
