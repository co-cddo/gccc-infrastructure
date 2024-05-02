import dataclasses
import os
from unittest import mock
from unittest.mock import Mock, call

import pytest
from lambda_.zendesk_backup import main as zendesk_backup
from lambda_.zendesk_backup.main import ZendeskObject


@pytest.fixture(autouse=True)
def mock_env_vars():
    with mock.patch.dict(os.environ, values={"S3_BUCKET": "test"}):
        yield


@pytest.fixture
def zendesk_backup_event():
    return {
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


@pytest.fixture
def json_ticket() -> dict[str, str]:
    return {
        "created_at": "2024-03-15T15:50:18Z"
    }


def test_athena_datetime(json_ticket):
    ticket_under_test = zendesk_backup.add_athena_datetimes(json_ticket)
    json_ticket.update({"created_at_athena": "2024-03-15 15:50:18"})
    assert ticket_under_test == json_ticket


def test_lambda_handler(zendesk_backup_event):
    path = "lambda_.zendesk_backup.main"
    with mock.patch(f"{path}.save_helpcentre") as mock_save_helpcentre, mock.patch(f"{path}.save_support") as mock_save_support:
        zendesk_backup.lambda_handler(**zendesk_backup_event)
        mock_save_helpcentre.assert_called_once_with()
        mock_save_support.assert_called_once_with()


def test_get_key():
    dictionary = {"html_url": "example.com/a/long/path"}
    assert zendesk_backup.get_key(dictionary) == "long/path"


@mock.patch("lambda_.zendesk_backup.main.zenpy_client")
@mock.patch("lambda_.zendesk_backup.main.s3_client")
def test_save_helpcenter(s3_client: Mock, zenpy_client: Mock):
    category = ZendeskCategory("example.com/example/path", id="category_id")
    section = ZendeskSection(category_id=category.id, html_url="example.com/section/path", id="section_id")
    article = ZendeskArticle(html_url="example.com/article/path", section_id=section.id, id="article_id")
    zenpy_client.return_value.help_center.categories.return_value = [category]
    zenpy_client.return_value.help_center.sections.return_value = [section]
    zenpy_client.return_value.help_center.articles.return_value = [article]
    zendesk_backup.save_helpcentre()
    s3_put: Mock = s3_client.return_value.put_object
    s3_put.assert_has_calls(
        [
            call(Body=b'{"html_url": "example.com/example/path", "id": "category_id"}', Bucket='test',
                 Key='helpcentre/example/path.json'),
            call(
                Body=b'{"html_url": "example.com/section/path", "id": "section_id", "category_id": "category_id"}',
                Bucket='test', Key='helpcentre/example/path/section/path.json'),
            call(
                Body=b'{"html_url": "example.com/article/path", "id": "article_id", "section_id": "section_id"}',
                Bucket='test', Key='helpcentre/example/path/section/path/article/path.json')
        ],
        any_order=True
    )


@mock.patch("lambda_.zendesk_backup.main.zenpy_client")
@mock.patch("lambda_.zendesk_backup.main.s3_client")
def test_save_helpcenter_when_no_key(s3_client: Mock, zenpy_client: Mock):
    category = ZendeskCategory(html_url="", id="category_id")
    section = ZendeskSection(category_id=category.id, html_url="", id="section_id")
    article = ZendeskArticle(html_url="", section_id=section.id, id="article_id")
    zenpy_client.return_value.help_center.categories.return_value = [category]
    zenpy_client.return_value.help_center.sections.return_value = [section]
    zenpy_client.return_value.help_center.articles.return_value = [article]
    zendesk_backup.save_helpcentre()
    s3_put: Mock = s3_client.return_value.put_object
    s3_put.assert_not_called()


def test_extract_substructure_when_no_key():
    section = ZendeskSection(category_id="category_id", id="section_id", html_url="")
    section_output = zendesk_backup.extract_substructure(
        "section",
        section,
        parent_id="category_id",
        parent_key="parent/key",
        article_ids=[]
    )
    assert section_output is None



@dataclasses.dataclass
class ZendeskCategory(ZendeskObject):
    id: str


@dataclasses.dataclass
class ZendeskSection(ZendeskObject):
    category_id: str


@dataclasses.dataclass
class ZendeskArticle(ZendeskObject):
    section_id: str
