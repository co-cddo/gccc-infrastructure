resource "aws_cloudwatch_event_rule" "lambda_event_rule" {
  name                = "lambda-zendesk-backup-event-rule"
  description         = "run scheduled every day"
  schedule_expression = "cron(0 3 * * ? *)"
  is_enabled          = terraform.workspace == "production"
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  arn  = aws_lambda_function.lambda.arn
  rule = aws_cloudwatch_event_rule.lambda_event_rule.name
}

resource "aws_lambda_permission" "allow_cloudwatch_to_call_lambda" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.lambda_event_rule.arn
}
