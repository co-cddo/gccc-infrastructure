import json

import zendesk
import hackerone


def lambda_handler(event, context):
    if "report_id" in event:
        hackerone_report = hackerone.get_hackerone_report(report_id=event["report_id"])
        if hackerone_report:
            print(json.dumps(hackerone_report, default=str))
            zid = zendesk.create_or_update_zendesk_ticket(hackerone_report)

            if not hackerone_report["issue_tracker_reference_id"]:
                hackerone.set_hackerone_reference(
                    hackerone_id=event["report_id"], zendesk_id=zid
                )
