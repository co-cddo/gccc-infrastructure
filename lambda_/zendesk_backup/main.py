import os
import json
from typing import Optional, Union

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


def get_key(obj: dict) -> str:
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


def save_helpcentre(article_ids: list = []):
    s3_bucket = get_s3_bucket()
    files = {}

    categories = zenpy_client().help_center.categories()
    for category in categories:
        category_key = get_key(category.to_dict())
        if category_key:
            if article_ids == []:
                files[category_key] = category.to_dict()

            sections = zenpy_client().help_center.sections(category_id=category.id)
            for section in sections:
                if section.category_id == category.id:
                    section_ref = get_key(section.to_dict())
                    if section_ref:
                        section_key = f"{category_key}/{section_ref}"
                        if article_ids == []:
                            files[section_key] = section.to_dict()

                        articles = zenpy_client().help_center.articles(
                            section_id=section.id
                        )
                        for article in articles:
                            if article.section_id == section.id:
                                article_ref = get_key(article.to_dict())
                                if article_ref:
                                    article_key = f"{section_key}/{article_ref}"
                                    if article_ids == [] or article.id in article_ids:
                                        files[article_key] = article.to_dict()

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
