import pytest


@pytest.fixture
def zendesk_backup_event():
    return {
        "_time": 1714446045.0087461,
        "context": "LambdaContext([aws_request_id=1f6df4b9-0a8e-434d-87e5-00f59f07c2f2,"
                   "log_group_name=/aws/lambda/zendesk-backup,log_stream_name=2024/04/30/["
                   "$LATEST]20ac904278394d5ba8163542dfa8e884,function_name=zendesk-backup,memory_limit_in_mb=512,"
                   "function_version=$LATEST,"
                   "invoked_function_arn=arn:aws:lambda:eu-west-2:468623140221:function:zendesk-backup,"
                   "client_context=None,identity=CognitoIdentity([cognito_identity_id=None,"
                   "cognito_identity_pool_id=None])])",
        "event": {
            "version": "0",
            "id": "1697296e-2030-dda6-7f4a-ac16427e291a",
            "detail-type": "Scheduled Event",
            "source": "aws.events",
            "account": "468623140221",
            "time": "2024-04-30T03:00:00Z",
            "region": "eu-west-2",
            "resources": [
                "arn:aws:events:eu-west-2:468623140221:rule/lambda-zendesk-backup-event-rule"
            ],
            "detail": {}
        }
    }
