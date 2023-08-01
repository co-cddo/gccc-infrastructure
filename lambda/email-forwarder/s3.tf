resource "aws_s3_bucket" "b" {
  provider = aws.eu_west_1
  bucket   = "mailbox.${local.email_domain}"

  tags = {
    Name = "mailbox.${local.email_domain}"
  }
}
resource "aws_s3_bucket_policy" "b" {
  provider = aws.eu_west_1
  bucket   = aws_s3_bucket.b.id

  policy = <<POLICY
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "ses.amazonaws.com"
            },
            "Action": "s3:PutObject",
            "Resource": "arn:aws:s3:::mailbox.${local.email_domain}/*",
            "Condition": {
                "StringEquals": {
                    "AWS:SourceAccount": "${data.aws_caller_identity.current.account_id}"
                },
                "StringLike": {
                    "AWS:SourceArn": "arn:aws:ses:*"
                }
            }
        }
    ]
}
POLICY
}
