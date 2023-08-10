import json

import zendesk
import hackerone


def lambda_handler(event, context):
    if "report_id" in event:
        hackerone_report = hackerone.get_hackerone_report(report_id=event["report_id"])
        if hackerone_report and hackerone_report.get("triaged_at", None) is not None:
            zid = zendesk.create_or_update_zendesk_ticket(hackerone_report)

            print(
                json.dumps(
                    {"hackerone_report": hackerone_report, "zendesk_id": zid},
                    default=str,
                )
            )

            if hackerone_report["issue_tracker_reference_id"]:
                print(
                    "Found existing reference_id in HackerOne:",
                    hackerone_report["issue_tracker_reference_id"],
                )
            else:
                print("Setting reference_id in HackerOne:", zid)
                hackerone.set_hackerone_reference(
                    hackerone_id=event["report_id"], zendesk_id=zid
                )
