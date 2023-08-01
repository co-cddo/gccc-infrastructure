provider "aws" {
  region = "eu-west-2"

  default_tags {
    tags = {
      "Service" : "email-forwarder",
      "Reference" : "https://github.com/co-cddo/gccc-infrastructure",
      "Environment" : terraform.workspace
    }
  }
}

terraform {
  backend "s3" {
    bucket = "gccc-core-security-tfstate"
    key    = "email-forwarder.tfstate"
    region = "eu-west-2"
  }
}

provider "aws" {
  region = "eu-west-1"
  alias  = "eu_west_1"

  assume_role {
    role_arn = terraform.workspace == "production" ? var.production_iam_role : var.staging_iam_role
  }

  default_tags {
    tags = {
      "Service" : "email-forwarder",
      "Reference" : "https://github.com/co-cddo/gccc-infrastructure",
      "Environment" : terraform.workspace
    }
  }
}
