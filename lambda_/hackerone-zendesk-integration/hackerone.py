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
    httpxresp = None
    with httpx.Client() as client:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Basic {get_hackerone_auth()}",
        }
        httpxresp = client.get(
            f"https://api.hackerone.com/v1/reports/{report_id}",
            headers=headers,
        )
    if not httpxresp:
        return None

    h1_dict = httpxresp.json() or {}
    h1_attrs = h1_dict.get("data", {}).get("attributes", {})
    h1_rels = h1_dict.get("data", {}).get("relationships", {})

    res = {
        "report_id": None,
        "report_url": None,
        "full_timestamps": {},
    }

    if h1_attrs or h1_rels:
        res["report_id"] = report_id
        res["report_url"] = f"https://hackerone.com/bugs?report_id={report_id}"
    else:
        return None

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
    ]:
        if x in h1_attrs:
            if (
                x.endswith("_at")
                and h1_attrs[x]
                and type(h1_attrs[x]) == str
                and "T" in h1_attrs[x].upper()
            ):
                res["full_timestamps"][x] = h1_attrs[x].upper()
                res[x] = h1_attrs[x].upper().split("T")[0]
            elif type(h1_attrs[x]) == str:
                res[x] = h1_attrs[x].strip()
            else:
                res[x] = h1_attrs[x]
        else:
            res[x] = None

    if res["state"] and res["main_state"]:
        res["state"] = f"{res['state'].title()} ({res['main_state'].title()})"
    else:
        res["state"] = "Unknown"

    res["cves"] = ", ".join(h1_attrs.get("cve_ids", []))

    h1_remguidance = (
        h1_rels.get("automated_remediation_guidance", {})
        .get("data", {})
        .get("attributes", {})
    )
    res["automated_remediation_guidance"] = h1_remguidance.get("reference", None)

    h1_program = h1_rels.get("program", {}).get("data", {}).get("attributes", {})
    res["program"] = h1_program.get("handle", None)

    h1_reporter = h1_rels.get("reporter", {}).get("data", {}).get("attributes", {})
    res["reporter_username"] = h1_reporter.get("username", None)

    h1_assignee = h1_rels.get("assignee", {}).get("data", {}).get("attributes", {})
    res["assigned_to"] = h1_assignee.get("name", None) or h1_assignee.get(
        "username", None
    )

    h1_weakness = h1_rels.get("weakness", {}).get("data", {}).get("attributes", {})
    res["weakness_name"] = h1_weakness.get("name", None)
    res["weakness_external_id"] = h1_weakness.get("external_id", "").upper()
    res["weakness_desc"] = h1_weakness.get("description", "").upper()

    h1_sev = h1_rels.get("severity", {}).get("data", {}).get("attributes", {})
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
            res[f"severity_{sx}"] = h1_sev[sx]
        else:
            res[f"severity_{sx}"] = None

    return res
