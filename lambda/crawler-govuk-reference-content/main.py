import json
import boto3
import time
import requests
import re
import math

s3 = boto3.resource("s3")
processed_bucket = "gccc-processed-a1205b9b-1e39-4d70"


def jprint(obj):
    new_obj = {}
    if type(obj) != dict:
        obj = {"message": str(obj)}
    if "_time" not in obj:
        new_obj["_time"] = time.time()
    for k in sorted(obj):
        new_obj[k] = obj[k]
    print(json.dumps(new_obj, default=str))


def lambda_handler(event, context):
    if "organisation" in event:
        fetch_organisations()
    elif "service" in event:
        # ...
        print("service")
    else:
        jprint("Don't know. Quitting.")


def fetch_services():
    try:
        count = 20
        api_url = f"https://www.gov.uk/api/search.json?filter_format=transaction&count={count}&start="
        init_services = requests.get(f"{api_url}0").json()

        services_raw = init_services["results"]
        entries = init_services["total"]
        jprint(f"Found {entries} entries")
        jprint("Processing from: 0")

        while len(services_raw) < entries:
            start = len(services_raw)
            jprint(f"Processing from: {start}")
            for_orgs = requests.get(f"{api_url}{start}").json()
            services_raw.extend(for_orgs["results"])

        for service in services_raw:
            link = service.get("link", None)
            if link:
                try:
                    service["content"] = requests.get(
                        f"https://www.gov.uk/api/content/{link.strip('/')}"
                    ).json()
                except Exception as e:
                    jprint(f"fetch_organisations:content API error:{e}")

                process_service(service)

    except Exception as e:
        jprint(f"fetch_services:search API error:{e}")


def process_service(service: dict):
    content_id = service.get("content", {}).get("content_id", None)
    if content_id:
        urls = []
        domains = []

        transaction_start_link = (
            service.get("content", {})
            .get("details", {})
            .get("transaction_start_link", None)
        )
        if transaction_start_link:
            urls.append(transaction_start_link)

        for url in urls:
            domains.extend(extract_domain(url))

        obj = {
            "id": content_id,
            "type": "service",
            "name": service.get("title", None),
            "description": service.get("description", None),
            "owning_organisations": service.get("organisation_content_ids", []),
            "urls": urls,
            "discovered_domains": list(set(domains)),
            "statuses": {
                "phase": service.get("content", {}).get("phase", None),
            },
            "created_at": athena_datetime(
                service.get("content", {}).get("first_published_at", None)
            ),
            "updated_at": athena_datetime(
                service.get("content", {}).get("public_updated_at", None)
            ),
        }

        # jprint(obj)

        simple_key = f"objects/all/{content_id}.json"
        full_key = f"objects/services/{content_id}.json"

        jprint(f"Writing s3://{processed_bucket}/{simple_key}")
        s3object = s3.Object(processed_bucket, simple_key)
        s3object.put(
            Body=(
                bytes(json.dumps({"id": content_id, "type": "service"}).encode("UTF-8"))
            )
        )

        jprint(f"Writing s3://{processed_bucket}/{full_key}")
        s3object = s3.Object(processed_bucket, full_key)
        s3object.put(Body=(bytes(json.dumps(obj).encode("UTF-8"))))


def fetch_organisations():
    try:
        api_url = "https://www.gov.uk/api/organisations"
        init_orgs = requests.get(api_url).json()

        organisations_raw = init_orgs["results"]
        jprint(f"Found {init_orgs['pages']} pages")
        jprint(f"Processing page: {1}")

        for page in range(2, init_orgs["pages"] + 1):
            jprint(f"Processing page: {page}")
            for_orgs = requests.get(f"{api_url}?page={page}").json()
            organisations_raw.extend(for_orgs["results"])

        organisation_pairs = {
            o["id"]: o["details"]["content_id"]
            for o in organisations_raw
            if o["id"] and o["details"] and "content_id" in o["details"]
        }

        for org in organisations_raw:
            slug = org.get("details", {}).get("slug", None)
            if slug:
                try:
                    org["content"] = requests.get(
                        f"https://www.gov.uk/api/content/government/organisations/{slug}"
                    ).json()
                except Exception as e:
                    jprint(f"fetch_organisations:content API error:{e}")

            process_organisation(org, organisation_pairs)
    except Exception as e:
        jprint(f"fetch_organisations:organisations API error:{e}")


def athena_datetime(d):
    if d:
        if type(d) == str:
            d = d.lower()
            if "t" in d:
                return d.replace("t", " ").replace("z", "").split(".")[0]
        else:
            return d
    return None


def extract_emails(obj: dict):
    res = []
    for item in obj.values():
        if type(item) == dict:
            res.extend(extract_emails(item))
        if type(item) == str:
            if "@" in item:
                email_search = re.finditer(
                    r"[\w\-\'\.]+@[\w\-\.]+\.\w+",
                    item,
                    re.IGNORECASE | re.MULTILINE,
                )
                for email_result in email_search:
                    email = email_result.group(0).lower()
                    if email not in res:
                        res.append(email)
    return list(set(res))


def extract_domain(text: str):
    res = []
    domain_search = re.finditer(
        r"(@|://)(?P<domain>[\w\-\.]+\.\w+)", text, re.IGNORECASE | re.MULTILINE
    )
    for domain_result in domain_search:
        domain = domain_result.groupdict().get("domain", None)
        if domain:
            domain = domain.lower()
            if domain.startswith("www."):
                res.append(domain[4:])
            else:
                res.append(domain)
    return res


def process_organisation(organisation: dict, organisation_pairs: dict):
    content_id = organisation.get("details", {}).get("content_id", None)
    if content_id:
        raw_key = f"govuk/organisations/{content_id}.json"
        jprint(f"Writing s3://{processed_bucket}/{raw_key}")
        s3object = s3.Object(processed_bucket, raw_key)
        s3object.put(
            Body=(bytes(json.dumps(organisation, default=str).encode("UTF-8")))
        )

        title = organisation.get("title", None)
        slug = organisation.get("details", {}).get("slug", None)

        discovered_emails = extract_emails(organisation)

        obj = {
            "id": content_id,
            "type": "organisation",
            "name": title,
            "description": organisation.get("format", None),
            "also_known_as": {},
            "other_identifiers": {},
            "parents": [],
            "children": [],
            "superseded": [],
            "superseding": [],
            "statuses": {
                "govuk_status": organisation.get("details", {}).get(
                    "govuk_status", None
                ),
                "govuk_closed_status": organisation.get("details", {}).get(
                    "govuk_closed_status", None
                ),
            },
            "discovered_emails": discovered_emails,
            "discovered_domains": [],
            "urls": [],
            "updated_at": athena_datetime(organisation.get("updated_at", None)),
        }

        web_url = organisation.get("web_url", None)
        if web_url:
            obj["urls"].append(web_url)

        for email in discovered_emails:
            obj["discovered_domains"].extend(extract_domain(email))

        for link in (
            organisation.get("content", {})
            .get("details", {})
            .get("social_media_links", [])
        ):
            if "href" in link:
                obj["urls"].append(link["href"])

                if link["href"].strip("/").endswith(".gov.uk"):
                    obj["discovered_domains"].extend(extract_domain(link["href"]))

        exempt_url = (
            organisation.get("content", {})
            .get("details", {})
            .get("organisation_govuk_status", {})
            .get("url", None)
        )
        if exempt_url:
            obj["urls"].append(exempt_url)
            obj["discovered_domains"].extend(extract_domain(exempt_url))

        obj["urls"] = list(set(obj["urls"]))
        obj["discovered_domains"] = list(set(obj["discovered_domains"]))

        if title:
            obj["also_known_as"]["govuk_title"] = title

        abbreviation = organisation.get("details", {}).get("abbreviation", None)
        if abbreviation:
            obj["also_known_as"]["govuk_abbreviation"] = abbreviation

        obj["other_identifiers"]["govuk_content_id"] = content_id

        if slug:
            obj["other_identifiers"]["govuk_slug"] = slug

        analytics_identifier = organisation.get("analytics_identifier", None)
        if analytics_identifier:
            obj["other_identifiers"][
                "govuk_analytics_identifier"
            ] = analytics_identifier

        for parent_org in organisation.get("parent_organisations", []):
            if "id" in parent_org and parent_org["id"] in organisation_pairs:
                obj["parents"].append(organisation_pairs[parent_org["id"]])

        for child_org in organisation.get("child_organisations", []):
            if "id" in child_org and child_org["id"] in organisation_pairs:
                obj["children"].append(organisation_pairs[child_org["id"]])

        for supd_org in organisation.get("superseded_organisations", []):
            if "id" in supd_org and supd_org["id"] in organisation_pairs:
                obj["superseded"].append(organisation_pairs[supd_org["id"]])

        for suping_org in organisation.get("superseding_organisations", []):
            if "id" in suping_org and suping_org["id"] in organisation_pairs:
                obj["superseding"].append(organisation_pairs[suping_org["id"]])

        # jprint(obj)

        simple_key = f"objects/all/{content_id}.json"
        full_key = f"objects/organisations/{content_id}.json"

        jprint(f"Writing s3://{processed_bucket}/{simple_key}")
        s3object = s3.Object(processed_bucket, simple_key)
        s3object.put(
            Body=(
                bytes(
                    json.dumps({"id": content_id, "type": "organisation"}).encode(
                        "UTF-8"
                    )
                )
            )
        )

        jprint(f"Writing s3://{processed_bucket}/{full_key}")
        s3object = s3.Object(processed_bucket, full_key)
        s3object.put(Body=(bytes(json.dumps(obj).encode("UTF-8"))))
