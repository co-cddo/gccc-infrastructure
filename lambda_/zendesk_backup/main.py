import dataclasses
import os
import json
from typing import Optional, Union, Literal, Any
import boto3
import time
import re
import functools
from zenpy import Zenpy


@functools.cache
def get_s3_bucket() -> str:
    return os.environ["S3_BUCKET"]


@functools.cache
def s3_client():
    return boto3.client("s3")


s3_helpcentre_prefix = "helpcentre/"
s3_support_prefix = "support/"


@functools.cache
def zenpy_client() -> Zenpy:
    zendesk_creds = {
        "email": os.environ["ZENDESK_API_EMAIL"],
        "token": os.environ["ZENDESK_API_KEY"],
        "subdomain": os.environ["ZENDESK_SUBDOMAIN"],
    }

    return Zenpy(**zendesk_creds)


def jprint(obj):
    new_obj = {}
    if type(obj) != dict:
        obj = {"message": str(obj)}
    if "_time" not in obj:
        new_obj["_time"] = time.time()
    for k in sorted(obj):
        new_obj[k] = obj[k]
    print(json.dumps(new_obj, default=str))


def get_key(obj: Optional[dict[str, Any]]) -> Optional[str]:
    """
    Get a URL from a dictionary and return the string consisting of the last two slash-separated elements, ie:
    >>> get_key({"html_url": "example.com/a/long/path"})
    long/path

    :param obj:
    :return:
    """
    res = None
    if obj and "html_url" in obj and "/" in obj["html_url"]:
        html_url_split = obj["html_url"].rsplit("/", 2)
        if len(html_url_split) == 3:
            res = f"{html_url_split[1]}/{html_url_split[2]}"
    return res


def add_athena_datetimes(json_dict: dict[str, Union[int, str, dict, list]]) -> dict:
    """
    Take a JSON formatted dictionary. Find a string that contains this pattern: a 2, followed by any number of digits,
    followed by a T/t, followed by two digits, followed by a colon. Having found that, replace the 't' with a space,
    remove the z (we are assuming there's a 'z' in this), and then split the string on the dots. Only take the first
    section of this newly split string, and add it back to the dictionary under the key f"{key}_athena"

    :param json_dict:
    :return:
    """
    res = {}
    for key, value in json_dict.items():
        if type(value) is str and re.match(r"(?i)2[\d\-]+t\d\d:", value):
            res[f"{key}_athena"] = (value.lower().replace("t", " ").replace("z", "").split(".")[0])

    res.update(json_dict)
    return res


def save_support(ticket_ids: Optional[list] = None):
    """
    Save support tickets from Zendesk. Additionally, add a datetime to them

    :param ticket_ids:
    :return:
    """
    s3_bucket = get_s3_bucket
    if ticket_ids:
        tickets = [zenpy_client().tickets(id=str(ticket_id)) for ticket_id in ticket_ids]
    else:
        tickets = zenpy_client().search_export(type="ticket")

    for ticket in tickets:
        # subject = re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9 ]", "", ticket.raw_subject))
        filename = f"gc3-{ticket.id}.json"
        key = f"{s3_support_prefix}tickets/{filename}"
        jprint(f"Saving 's3://{s3_bucket}/{key}'")

        dobj = add_athena_datetimes(ticket.to_dict())

        s3_client().put_object(
            Body=json.dumps(dobj, default=str).encode("utf-8"),
            Bucket=s3_bucket,
            Key=key,
        )


@dataclasses.dataclass
class ZendeskObject:
    html_url: str
    id: str

    to_dict = dataclasses.asdict


@dataclasses.dataclass
class ZendeskCategory(ZendeskObject):
    id: str


@dataclasses.dataclass
class ZendeskSection(ZendeskObject):
    category_id: str


@dataclasses.dataclass
class ZendeskArticle(ZendeskObject):
    section_id: str


ObjectTypes = Literal["article", "section"]


def get_relations(subject: ObjectTypes) -> dict[str, ObjectTypes]:
    relations = {
        "article": {
            "parent": "section"
        },
        "section": {
            "parent": "category"
        }
    }
    return relations[subject]


def extract_substructure(object_type: ObjectTypes, zendesk_object: ZendeskObject, parent_id: str, parent_key: str,
                         article_ids: list) -> tuple[dict, str]:
    relations = get_relations(object_type)
    parent_type = relations["parent"]
    substructure = {}
    parent_type_id = f"{parent_type}_id"
    if zendesk_object.__getattribute__(parent_type_id) == parent_id:
        object_ref = get_key(zendesk_object.to_dict())
        if object_ref:
            object_key = f"{parent_key}/{object_ref}"
            if article_ids == [] or zendesk_object.id in article_ids:
                substructure = {object_key: zendesk_object.to_dict()}
    return substructure, object_key


def extract_helpcenter(article_ids: list) -> dict[str, dict]:
    """
    This takes a complex, nested set of dictionaries and flattens them into a more simple structure. With more time,
    we could make this recursive and very simple. However, it's good enough as it is

    :param article_ids:
    :return:
    """
    files = {}

    categories = zenpy_client().help_center.categories()
    for category in categories:
        category_key = get_key(category.to_dict())
        if category_key:
            if not article_ids:
                files[category_key] = category.to_dict()

            sections = zenpy_client().help_center.sections(category_id=category.id)
            for section in sections:
                section_file, section_key = extract_substructure(
                    object_type="section",
                    zendesk_object=section,
                    parent_id=category.id,
                    parent_key=category_key,
                    article_ids=article_ids
                )
                files.update(section_file)

                articles = zenpy_client().help_center.articles(section_id=section.id)
                for article in articles:
                    article_file, _ = extract_substructure(
                        object_type="article",
                        zendesk_object=article,
                        parent_id=section.id,
                        parent_key=section_key,
                        article_ids=article_ids,
                    )
                    files.update(article_file)
    return files


def save_helpcentre(article_ids=None):
    if article_ids is None:
        article_ids = []

    s3_bucket = get_s3_bucket()
    files = extract_helpcenter(article_ids)

    for file in files:
        filename = f"{file}.json"
        file_obj = files[file]

        html = None
        html_filename = None
        if "body" in file_obj:
            html = file_obj["body"]
            html_filename = f"{file}.html"

        wdt = add_athena_datetimes(file_obj)

        jprint(f"Saving 's3://{s3_bucket}/{s3_helpcentre_prefix}{filename}'")
        s3_client().put_object(
            Body=json.dumps(wdt, default=str).encode("utf-8"),
            Bucket=s3_bucket,
            Key=f"{s3_helpcentre_prefix}{filename}",
        )
        if html and html_filename:
            jprint(f"Saving 's3://{s3_bucket}/{s3_helpcentre_prefix}{html_filename}'")
            s3_client().put_object(
                Body=html.encode("utf-8"),
                Bucket=s3_bucket,
                Key=f"{s3_helpcentre_prefix}{html_filename}",
            )


def lambda_handler(event, context):
    """
    This is the lambda handler for the code above. At the moment, the only path that's covered is the final 'else'. In
    future, we can send slightly different events through the EventBridge cron job.

    :param event:
    :param context:
    :return:
    """
    try:
        jprint({"event": event, "context": context})

        do_save_support_ticket_ids = []
        do_save_helpcentre_article_ids = []

        if "ticket_id" in event:
            do_save_support_ticket_ids = [event["ticket_id"]]
            save_support(ticket_ids=do_save_support_ticket_ids)
        elif "only_support" in event and event["only_support"]:
            save_support()
        elif "article_id" in event:
            do_save_helpcentre_article_ids = [event["article_id"]]
            save_helpcentre(article_ids=do_save_helpcentre_article_ids)
        elif "only_helpcentre" in event and event["only_helpcentre"]:
            save_helpcentre()
        else:
            save_helpcentre()
            save_support()
    except Exception as e:
        jprint(e)
