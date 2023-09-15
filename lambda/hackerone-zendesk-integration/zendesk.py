import os
import json
import httpx
import time

from zenpy import Zenpy
from zenpy.lib.api_objects import Ticket, User, Comment, CustomField

zendesk_creds = {
    "email": os.environ["ZENDESK_API_EMAIL"],
    "token": os.environ["ZENDESK_API_KEY"],
    "subdomain": os.environ["ZENDESK_SUBDOMAIN"],
}

zenpy_client = Zenpy(**zendesk_creds)

zendesk_email = os.environ["ZENDESK_EMAIL"]  # what the "from" email is
zendesk_requester = 13633022984593  # HackerOne Automation user
# zendesk_group = 10980471236113  # Vulnerability Management Team; use Zendesk Triggers to assign!
zendesk_ticket_form = 12219491114257  # Vulnerability Report


def get_zendesk_ticket_by_id(zendesk_id):
    return zenpy_client.tickets(id=str(zendesk_id))


def get_zendesk_ticket_by_hackerone_id(hackerone_id):
    resp = None
    se = zenpy_client.search_export(
        type="ticket", custom_field_13630395133585=str(hackerone_id)
    )
    for ticket in se:
        if ticket:
            resp = ticket
            break
    return resp


def create_or_update_zendesk_ticket(h1obj: dict):
    zticket = None

    if h1obj["issue_tracker_reference_id"]:
        zticket = get_zendesk_ticket_by_id(h1obj["issue_tracker_reference_id"])
        if not zticket:
            print("Reference ID exists, but ticket couldn't be found. Quitting.")
            return None
    else:
        zticket = get_zendesk_ticket_by_hackerone_id(h1obj["report_id"])

    if not zticket:
        print("Zendesk ticket doesn't exist, creating...")
        current_datetime = time.strftime("%Y-%m-%d %H:%M", time.localtime())
        tc_resp = zenpy_client.tickets.create(
            Ticket(
                description="HackerOne report",
                subject=h1obj["title"],
                comment=Comment(
                    body=f"HackerOne vulnerability information at {current_datetime}: {h1obj['vulnerability_information']}",
                    public=False,
                    author_id=zendesk_requester,
                ),
                recipient=zendesk_email,
                submitter_id=zendesk_requester,
                requester_id=zendesk_requester,
                # group_id=zendesk_group, # use Zendesk Triggers to assign!
                ticket_form_id=zendesk_ticket_form,
            )
        )
        zticket = tc_resp.ticket

        zticket.comment = Comment(
            body=f"Created automatically from HackerOne report: {h1obj['report_url']}\n\nNote: custom fields (left) and the subject are synchronised automatically from HackerOne.\n\nNext steps:\n - find the system or service owner\n - change the 'Requester' to the main contact found (use 'CC' in the top right of the comments box to include additional people)\n - make sure the 'Select a Reply From' has the correct vm email selected\n - use 'Public reply' to inform the requester and CCs of the report\n - use HackerOne to keep the security researcher informed",
            public=False,
            author_id=zendesk_requester,
        )

    full_timestamps = []
    for ts in h1obj["full_timestamps"]:
        tss = f"{ts.title().replace('_', ' ')}:\n{h1obj['full_timestamps'][ts]}"
        full_timestamps.append(tss)
    h1_timestamps_str = "\n".join(full_timestamps)

    zticket.subject = h1obj["title"]
    zticket.custom_fields = [
        CustomField(id=13630395133585, value=h1obj["report_id"]),
        CustomField(id=13630685790097, value=h1obj["report_url"]),
        CustomField(id=13630481911185, value=h1obj["closed_at"]),
        CustomField(id=13630429201169, value=h1obj["created_at"]),
        CustomField(id=13630470495633, value=h1obj["triaged_at"]),
        CustomField(id=13630631663249, value=h1obj["last_activity_at"]),
        CustomField(id=13640893129105, value=h1obj["last_public_activity_at"]),
        CustomField(id=13630456602001, value=h1obj["state"]),
        CustomField(id=13642012332689, value=h1obj["severity_rating"]),
        CustomField(id=13630515883409, value=h1obj["cves"]),
        CustomField(id=13630486759697, value=h1obj["weakness_name"]),
        CustomField(id=13630488020113, value=h1obj["weakness_external_id"]),
        # CustomField(id=13630617594897, value=h1obj["weakness_desc"]),
        CustomField(id=18597528066321, value=h1obj["automated_remediation_guidance"]),
        CustomField(id=18597505386129, value=h1obj["program"]),
        CustomField(id=18594542189457, value=h1obj["assigned_to"]),
        CustomField(id=13641072614417, value=h1obj["reporter_username"]),
        CustomField(id=18597329201681, value=h1_timestamps_str),
    ]
    zenpy_client.tickets.update(zticket)

    print(json.dumps({"zendesk_ticket": zticket.to_dict()}, default=str))

    return zticket.id
