import os
import json
import base64
import httpx

hackerone_api_user = os.environ["HACKERONE_API_USER"]
hackerone_api_pass = os.environ["HACKERONE_API_PASS"]


def get_hackerone_auth():
    return base64.b64encode(
        f"{hackerone_api_user}:{hackerone_api_pass}".encode("utf-8")
    ).decode("utf-8")


def set_hackerone_reference(hackerone_id, zendesk_id):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {get_hackerone_auth()}",
    }
    data = {
        "data": {
            "type": "issue-tracker-reference-id",
            "attributes": {
                "reference": str(zendesk_id),
                "message": f"https://my.gc3.security.gov.uk/agent/tickets/{zendesk_id}",
            },
        }
    }

    hackerone_resp = None
    with httpx.Client() as client:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Basic {get_hackerone_auth()}",
        }
        hackerone_resp = client.post(
            f"https://api.hackerone.com/v1/reports/{hackerone_id}/issue_tracker_reference_id",
            headers=headers,
            json=data,
        )
    print("set_hackerone_reference:", hackerone_resp)


def get_hackerone_report(report_id):
    h1obj = {}
    hackerone_resp = None
    with httpx.Client() as client:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Basic {get_hackerone_auth()}",
        }
        hackerone_resp = client.get(
            f"https://api.hackerone.com/v1/reports/{report_id}",
            headers=headers,
        )

    if hackerone_resp:
        h1resp = hackerone_resp.json()
        h1_attrs = h1resp["data"]["attributes"]

    if h1_attrs:
        h1obj = {
            "report_id": report_id,
            "report_url": f"https://hackerone.com/bugs?report_id={report_id}",
            "weakness_name": None,
            "weakness_external_id": None,
            "weakness_desc": None,
            "severity_rating": None,
            "severity_score": None,
            "severity_attack_complexity": None,
            "severity_attack_vector": None,
            "severity_availability": None,
            "severity_confidentiality": None,
            "severity_integrity": None,
            "severity_privileges_required": None,
            "severity_user_interaction": None,
            "severity_scope": None,
        }

        for x in [
            "issue_tracker_reference_id",
            "issue_tracker_reference_url",
            "title",
            "vulnerability_information",
            "main_state",
            "state",
            "last_activity_at",
            "last_public_activity_at",
            "created_at",
            "triaged_at",
            "closed_at",
            "last_public_activity_at",
        ]:
            if x in h1_attrs:
                if x.endswith("_at") and h1_attrs[x] and "T" in h1_attrs[x]:
                    h1_attrs[x] = h1_attrs[x].split("T")[0]
                h1obj[x] = h1_attrs[x]
            else:
                h1obj[x] = None

        if h1obj["state"] and h1obj["main_state"]:
            h1obj["state"] = f"{h1obj['state'].title()} ({h1obj['main_state'].title()})"
        else:
            h1obj["state"] = "Unknown"

        h1obj["cves"] = ", ".join(h1resp["data"]["attributes"]["cve_ids"])

        if (
            "weakness" in h1resp["data"]["relationships"]
            and "data" in h1resp["data"]["relationships"]["weakness"]
            and "attributes" in h1resp["data"]["relationships"]["weakness"]["data"]
        ):
            h1_weakness = h1resp["data"]["relationships"]["weakness"]["data"][
                "attributes"
            ]
            h1obj["weakness_name"] = h1_weakness["name"]
            h1obj["weakness_external_id"] = h1_weakness["external_id"].upper()
            h1obj["weakness_desc"] = h1_weakness["description"]

        if (
            "severity" in h1resp["data"]["relationships"]
            and "data" in h1resp["data"]["relationships"]["severity"]
            and "attributes" in h1resp["data"]["relationships"]["severity"]["data"]
        ):
            h1_sev = h1resp["data"]["relationships"]["severity"]["data"]["attributes"]

            for sx in [
                "rating",
                "score",
                "attack_complexity",
                "attack_vector",
                "availability",
                "confidentiality",
                "integrity",
                "privileges_required",
                "user_interaction",
                "scope",
            ]:
                if sx in h1_sev:
                    h1obj[f"severity_{sx}"] = h1_sev[sx]

    return h1obj
