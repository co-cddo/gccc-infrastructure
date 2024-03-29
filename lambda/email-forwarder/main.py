import os
import boto3
import json
import time
import random
import email

from botocore.exceptions import ClientError
from botocore.client import Config

region = os.getenv("Region", None)
incoming_email_bucket = os.getenv("MailS3Bucket", None)
system_domain = os.getenv("MailSenderDomain", None)

client_s3 = boto3.client("s3", config=Config(signature_version="s3v4"))

forward_mapping = {
    "contact": {
        "system_email": "contact@gccc.zendesk.com",
        "reply_from": "contact@gc3.security.gov.uk",
    },
    "security": {
        "system_email": "contact@gccc.zendesk.com",
        "reply_from": "contact@gc3.security.gov.uk",
    },
    "im": {
        "system_email": "im@gccc.zendesk.com",
        "reply_from": "im@gc3.security.gov.uk",
    },
    "report": {
        "system_email": "im@gccc.zendesk.com",
        "reply_from": "im@gc3.security.gov.uk",
    },
    "incident": {
        "system_email": "im@gccc.zendesk.com",
        "reply_from": "im@gc3.security.gov.uk",
    },
    "incidents": {
        "system_email": "im@gccc.zendesk.com",
        "reply_from": "im@gc3.security.gov.uk",
    },
    "vm": {
        "system_email": "vm@gccc.zendesk.com",
        "reply_from": "vm@gc3.security.gov.uk",
    },
    "vulnerability": {
        "system_email": "vm@gccc.zendesk.com",
        "reply_from": "vm@gc3.security.gov.uk",
    },
    "vulnerabilities": {
        "system_email": "vm@gccc.zendesk.com",
        "reply_from": "vm@gc3.security.gov.uk",
    },
    "data": {
        "system_email": "data@gccc.zendesk.com",
        "reply_from": "data@gc3.security.gov.uk",
    },
    "threat": {
        "system_email": "threat@gccc.zendesk.com",
        "reply_from": "threat@gc3.security.gov.uk",
    },  
    "tm": {
        "system_email": "threat@gccc.zendesk.com",
        "reply_from": "threat@gc3.security.gov.uk",
    },
    "tech": {
        "system_email": "tech@gccc.zendesk.com",
        "reply_from": "tech@gc3.security.gov.uk",
    },
    "ollie": {
        "system_email": "oliver.chalk@digital.cabinet-office.gov.uk",
        "reply_from": "ollie@gc3.security.gov.uk",
    },
}

_asam = os.getenv("allowed_send_as_emails", "")
allowed_send_as_emails = [x.lower().strip() for x in _asam.split(",") if "@" in x]


def get_forward_mappings(email: str) -> dict:
    for fm in forward_mapping:
        if email.startswith(f"{fm}@"):
            return forward_mapping[fm]
    return {}


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


def get_send_as_destinations_from_plain_text(text):
    res = {
        "to": [],
        "cc": [],
        "bcc": [],
        "all_destinations": [],
    }

    if type(text) == bytes:
        text = text.decode("utf-8")

    if not text or type(text) != str:
        return res

    current_processor = None
    for line in text.split("\n"):
        nl = line.lower().strip()
        if nl.startswith("---"):
            break
        elif nl.startswith("to:"):
            nl = nl[3:]
            current_processor = "to"
        elif nl.startswith("cc:"):
            nl = nl[3:]
            current_processor = "cc"
        elif nl.startswith("bcc:"):
            nl = nl[4:]
            current_processor = "bcc"
        if current_processor and "@" in nl:
            for _eea in extract_email_addresses(nl):
                if _eea not in res[current_processor]:
                    res[current_processor].append(_eea)
                    if _eea not in res["all_destinations"]:
                        res["all_destinations"].append(_eea)
    return res


def process_send_as_email(mailobject, from_address: str = None, filename: str = None):
    res = {
        "from": from_address,
        "send_as": False,
        "to": [],
        "cc": [],
        "bcc": [],
        "all_destinations": [],
        "new_mailobject": None,
    }

    if not filename or not from_address:
        return res

    if not mailobject.is_multipart():
        return res

    new_email = email.message.EmailMessage()
    new_email["Subject"] = mailobject.get(
        "Subject", "Government Cyber Coordination Centre"
    )
    new_email["From"] = from_address

    new_parts = []

    recipient_attachment = None
    for part in mailobject.walk():
        part_fn = part.get_filename()

        if part_fn is not None and part_fn.startswith(filename):
            recipient_attachment = part.get_payload(decode=True)

        elif not part.is_multipart() and not part_fn:
            content = part.get_payload(decode=True)
            new_parts.append(
                {
                    "content": content,
                    "maintype": part.get_content_maintype(),
                    "subtype": part.get_content_subtype(),
                }
            )
        # get and add attachments here

    print("recipient_attachment:", recipient_attachment)

    if recipient_attachment:
        res.update(get_send_as_destinations_from_plain_text(recipient_attachment))
        print("res:", res)
        if len(res["all_destinations"]) > 0:
            res["send_as"] = True
            if res["to"]:
                new_email["To"] = ", ".join(res["to"])
            if res["cc"]:
                new_email["Cc"] = ", ".join(res["cc"])
            if res["bcc"]:
                new_email["Bcc"] = ", ".join(res["bcc"])

            for new_part in new_parts:
                new_email.add_alternative(
                    new_part["content"],
                    maintype=new_part["maintype"],
                    subtype=new_part["subtype"],
                )

            res["new_mailobject"] = new_email

    return res


def extract_email_addresses(raw_email):
    res = []
    if raw_email and type(raw_email) == str:
        raw_email = raw_email.lower().strip()
        if "@" in raw_email:
            if "," in raw_email:
                for esplit in raw_email.split(","):
                    res.extend(extract_email_addresses(esplit))
            elif "<" in raw_email:
                res.append(raw_email.split("<", 1)[1].strip(">"))
            else:
                res.append(raw_email)
    return res


def create_message(file_dict, new_to_email, original_recipient):
    message = {}

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

    sender_email = None
    _sender_emails = extract_email_addresses(sender)
    if _sender_emails and len(_sender_emails) == 1:
        sender_email = _sender_emails[0]

    print("sender_email:", sender_email)

    is_send_as = False
    if sender_email and sender_email in allowed_send_as_emails:
        print("sender_email in allowed_send_as_emails!")
        psae = process_send_as_email(
            mailobject=mailobject, from_address=original_recipient, filename="send_as"
        )
        print(psae)
        if psae["send_as"]:
            is_send_as = True
            message = {
                "Source": psae["from"],
                "Destinations": psae["all_destinations"],
                "Data": psae["new_mailobject"].as_string(),
            }

    if not is_send_as:
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
            "Destinations": [new_to_email],
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
            Destinations=message["Destinations"],
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

    # initial delay waiting for s3 and tagging
    time.sleep(random.randrange(2, 10))

    s3_key = event["Records"][0]["ses"]["mail"]["messageId"]

    file_dict = get_message_from_s3(s3_key)
    if not file_dict:
        return

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
            mapped_email = get_forward_mappings(dest)
            if mapped_email:
                # Create the message.
                message = create_message(
                    file_dict,
                    mapped_email["system_email"],
                    mapped_email["reply_from"],
                )
                if message:
                    print(message)
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
