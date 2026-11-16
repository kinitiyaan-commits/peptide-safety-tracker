"""User-initiated export. Exports are scoped to a single user only."""

import csv
import io
import json

from . import service


def export_user_data(db_path, user_id, fmt="json"):
    """Return (payload_bytes, media_type, suggested_filename)."""
    data = {
        "exported_at": service._now_iso(),
        "user_id": user_id,
        "tracking_goals": service.get_user_goals(db_path, user_id),
        "usage_log": service.list_usage(db_path, user_id),
        "symptoms": service.list_symptoms(db_path, user_id),
        "observations": service.list_observations(db_path, user_id),
        "reminders": service.list_reminders(db_path, user_id),
    }
    if fmt == "json":
        payload = json.dumps(data, indent=2).encode("utf-8")
        return payload, "application/json", f"peptide_data_user{user_id}.json"

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        for section, rows in (("usage_log", data["usage_log"]),
                              ("symptoms", data["symptoms"]),
                              ("observations", data["observations"]),
                              ("reminders", data["reminders"])):
            if rows:
                headers = list(rows[0].keys())
                writer.writerow([section] + headers)
                for row in rows:
                    writer.writerow([section] + [_csv_val(row[h]) for h in headers])
        payload = buf.getvalue().encode("utf-8")
        return payload, "text/csv", f"peptide_data_user{user_id}.csv"

    raise ValueError("format must be 'json' or 'csv'")


def _csv_val(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value
