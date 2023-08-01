import os
import boto3
import email
import json
import base64
import time
import random

from botocore.exceptions import ClientError
from botocore.client import Config

region = os.environ["Region"]
incoming_email_bucket = os.environ["MailS3Bucket"]
system_domain = os.environ["MailSenderDomain"]

client_s3 = boto3.client("s3", config=Config(signature_version="s3v4"))

forward_mapping = {
    "contact": ["contact@gccc.zendesk.com"],
    "im": ["im@gccc.zendesk.com"],
    "report": ["im@gccc.zendesk.com"],
    "vm": ["vm@gccc.zendesk.com"],
    "data": ["data@gccc.zendesk.com"],
    "ollie": ["oliver.chalk@digital.cabinet-office.gov.uk"],
}


def get_forward_mappings(email: str):
    for f in forward_mapping:
        if email.startswith(f):
            return forward_mapping[f]
        if email.endswith(f):
            return forward_mapping[f]
    return []


def get_message_from_s3(object_path):
    object_http_path = (
        f"https://s3.{region}.amazonaws.com/{incoming_email_bucket}/{object_path}"
    )

    # Get the email object from the S3 bucket.
    object_s3 = client_s3.get_object(Bucket=incoming_email_bucket, Key=object_path)
    # Read the content of the message.
    file = object_s3["Body"].read()

    file_dict = {"file": file, "path": object_http_path}
    print(json.dumps(file_dict, default=str))

    return file_dict


def create_message(file_dict, new_to_email, original_recipient):
    # Parse the email body.
    mailobject = email.message_from_bytes(file_dict["file"])

    sender = mailobject.get("From")
    if sender is None:
        sender = mailobject.get("Reply-To")
    if sender is None:
        sender = mailobject.get("Sender")
    if sender is None:
        sender = mailobject.get("Return-Path")
    if sender is None:
        sender = mailobject.get("X-Original-Sender")

    if sender is None:
        return None

    sender_email = sender
    if "<" in sender_email:
        sender_email = sender_email.split("<", 1)[1].strip(">")

    zendesk_reply = False

    new_headers = []
    for x in mailobject._headers:
        if x[0] in ["Received-SPF", "Authentication-Results"]:
            new_headers.append((f"X-SES-{x[0]}", x[1]))
        if not zendesk_reply and x[0] in ["References", "In-Reply-To"]:
            if "zendesk.com" in x[1]:
                zendesk_reply = True
        if x[0] not in [
            "Received-SPF",
            "Authentication-Results",
            "DKIM-Signature",
            "From",
            "Reply-To",
            "Return-Path",
            "To",
            "Sender",
            "X-Original-Sender",
        ]:
            new_headers.append(x)

    mailobject._headers = new_headers

    mailobject.add_header(
        "From", sender if system_domain in sender else original_recipient
    )
    mailobject.add_header("Reply-To", sender)
    mailobject.add_header("To", original_recipient)

    # b64 = base64.standard_b64encode(mailobject.as_bytes())

    message = {
        "Source": original_recipient,
        "Destinations": new_to_email,
        "Data": mailobject.as_string(),
    }

    return message


def send_email(message):
    # Create a new SES client.
    client_ses = boto3.client("ses", region)

    # Send the email.
    try:
        # Provide the contents of the email.
        response = client_ses.send_raw_email(
            Source=message["Source"],
            Destinations=[message["Destinations"]],
            RawMessage={"Data": message["Data"]},
        )

    # Display an error if something goes wrong.
    except ClientError as e:
        output = e.response["Error"]["Message"]
    else:
        output = "Email sent! Message ID: " + response["MessageId"]

    return output


def lambda_handler(event, context):
    print(json.dumps(event, default=str))

    # initial delay waiting for s3
    time.sleep(1)

    s3_key = event["Records"][0]["ses"]["mail"]["messageId"]

    file_dict = get_message_from_s3(s3_key)
    if not file_dict:
        return

    # Check for tag
    time.sleep(float(random.randrange(50, 501) / 100))
    tag_resp = client_s3.get_object_tagging(Bucket=incoming_email_bucket, Key=s3_key)
    email_processed = False
    if "TagSet" in tag_resp:
        for kv in tag_resp["TagSet"]:
            if kv["Key"] == "processed":
                email_processed = True
                break

    if not email_processed:
        destinations = [
            r.lower() for r in event["Records"][0]["ses"]["receipt"]["recipients"]
        ]
        for dest in destinations:
            for mapped_email in get_forward_mappings(dest):
                # Create the message.
                message = create_message(file_dict, mapped_email, dest)
                if message:
                    # Send the email and print the result.
                    result = send_email(message)
                    print(result)

        tag_proc_resp = client_s3.put_object_tagging(
            Bucket=incoming_email_bucket,
            Key=s3_key,
            Tagging={
                "TagSet": [
                    {"Key": "processed", "Value": "true"},
                ]
            },
        )
