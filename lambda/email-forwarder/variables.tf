data "aws_caller_identity" "current" {
  provider = aws.eu_west_1
}

locals {
  lambda_name = "email-forwarding-${terraform.workspace}"
  iam_role    = "email-forwarding-lambda-role-${terraform.workspace}"
  iam_policy  = "email-forwarding-lambda-policy-${terraform.workspace}"

  email_domain = terraform.workspace == "production" ? "gc3.security.gov.uk" : "gc3-staging.security.gov.uk"
}

variable "staging_iam_role" {
  sensitive = true
  type      = string
}

variable "production_iam_role" {
  sensitive = true
  type      = string
}
