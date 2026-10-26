
# import frappe
# from collections import defaultdict
# from datetime import datetime

# from frappe.utils import add_days, getdate, nowdate

# from team_office_attendance.utils.etimeoffice_api import (
#     fetch_punch_data,
# )


# API_DEVICE_PREFIX = "TEAM_OFFICE_API:"


# def _get_api_credentials():
#     """Read API credentials from the site's private configuration."""
#     corporate_id = frappe.conf.get("etimeoffice_corporate_id")
#     username = frappe.conf.get("etimeoffice_username")
#     password = frappe.conf.get("etimeoffice_password")

#     if not all([corporate_id, username, password]):
#         frappe.throw(
#             "eTimeOffice API credentials missing. "
#             "Configure etimeoffice_corporate_id, "
#             "etimeoffice_username and etimeoffice_password "
#             "in the site's configuration."
#         )

#     return corporate_id, username, password


# def _parse_punch_time(value):
#     """Convert eTimeOffice PunchDate into a Python datetime."""
#     if not value:
#         return None

#     try:
#         return datetime.strptime(value.strip(), "%d/%m/%Y %H:%M:%S")
#     except (ValueError, AttributeError):
#         frappe.log_error(
#             title="Invalid eTimeOffice PunchDate",
#             message=f"Could not parse PunchDate: {value!r}",
#         )
#         return None


# def _expected_log_types(punches):
#     """
#     First punch = IN.
#     Last punch = OUT when there is more than one punch.
#     Middle punches alternate; last punch is always OUT.
#     A single punch remains IN (exit missing).
#     """
#     count = len(punches)

#     if count == 1:
#         return ["IN"]

#     types = []
#     for index in range(count):
#         if index == 0:
#             types.append("IN")
#         elif index == count - 1:
#             types.append("OUT")
#         else:
#             types.append("OUT" if index % 2 else "IN")

#     return types


# def sync_etimeoffice_punches(dry_run=True):
#     """
#     Fetch eTimeOffice website API punches and prepare Employee Checkins.

#     dry_run=True:
#         Fetch and inspect data only. No ERPNext records are saved.

#     dry_run=False:
#         Create missing API checkins and reconcile log_type only on
#         records previously created by this API integration.
#         Existing records from other sources are never modified.
#     """
#     corporate_id, username, password = _get_api_credentials()

#     mappings = frappe.get_all(
#         "Team Office Employee Mapping",
#         filters={"enabled": 1},
#         fields=["etimeoffice_employee_code", "employee"],
#         order_by="etimeoffice_employee_code asc",
#     )

#     if not mappings:
#         return {
#             "status": "No enabled employee mappings found",
#             "dry_run": dry_run,
#             "created": 0,
#             "skipped": 0,
#             "errors": [],
#         }

#     # Re-fetch a rolling 7-day period to catch missed API syncs.
#     end_date = getdate(nowdate())
#     start_date = getdate(add_days(end_date, -6))

#     from_date = f"{start_date.strftime('%d/%m/%Y')}_00:00"
#     to_date = f"{end_date.strftime('%d/%m/%Y')}_23:59"

#     punches_by_employee_day = defaultdict(dict)
#     errors = []
#     records_read = 0

#     # Phase 1: Fetch data from the website API. No writes in this phase.
#     for mapping in mappings:
#         employee_code = mapping.etimeoffice_employee_code
#         employee = mapping.employee

#         try:
#             response = fetch_punch_data(
#                 corporate_id=corporate_id,
#                 username=username,
#                 password=password,
#                 employee_code=employee_code,
#                 from_date=from_date,
#                 to_date=to_date,
#             )

#             if not isinstance(response, dict):
#                 raise ValueError("API response is not a JSON object")

#             if response.get("Error"):
#                 raise ValueError(
#                     str(response.get("Msg") or "API returned an error")
#                 )

#             api_punches = response.get("PunchData") or []

#             if not isinstance(api_punches, list):
#                 raise ValueError("API PunchData is not a list")

#             for item in api_punches:
#                 records_read += 1

#                 # Prevent a response for another employee from being
#                 # assigned to the current mapping.
#                 if str(item.get("Empcode", "")).strip() != str(
#                     employee_code
#                 ).strip():
#                     errors.append(
#                         f"{employee_code}: API returned a different "
#                         f"employee code {item.get('Empcode')!r}"
#                     )
#                     continue

#                 punch_time = _parse_punch_time(item.get("PunchDate"))
#                 if not punch_time:
#                     continue

#                 if not (start_date <= punch_time.date() <= end_date):
#                     continue

#                 day_key = (employee, punch_time.date())

#                 # Timestamp is the deduplication key within this
#                 # employee's API response.
#                 punches_by_employee_day[day_key][punch_time] = {
#                     "employee": employee,
#                     "employee_code": employee_code,
#                     "time": punch_time,
#                     "name": item.get("Name"),
#                 }

#         except Exception as exc:
#             errors.append(f"{employee_code}: {str(exc)}")

#     # Do not write partial data if any employee's API fetch failed.
#     if errors:
#         return {
#             "status": "API errors found; no records were saved",
#             "dry_run": dry_run,
#             "date_from": str(start_date),
#             "date_to": str(end_date),
#             "records_read": records_read,
#             "created": 0,
#             "skipped": 0,
#             "errors": errors,
#         }

#     created = 0
#     skipped = 0
#     updated_api_log_types = 0
#     preview = []

#     # Phase 2: Prepare each employee's punches in chronological order.
#     for (employee, punch_date), punch_dict in sorted(
#         punches_by_employee_day.items(),
#         key=lambda entry: (entry[0][0], entry[0][1]),
#     ):
#         punches = sorted(
#             punch_dict.values(),
#             key=lambda item: item["time"],
#         )
#         expected_types = _expected_log_types(punches)

#         for punch, expected_type in zip(punches, expected_types):
#             punch_time = punch["time"]
#             employee_code = punch["employee_code"]
#             api_device_id = f"{API_DEVICE_PREFIX}{employee_code}"

#             preview.append(
#                 {
#                     "employee": employee,
#                     "employee_code": employee_code,
#                     "time": str(punch_time),
#                     "log_type": expected_type,
#                 }
#             )

#             existing = frappe.db.get_value(
#                 "Employee Checkin",
#                 {"employee": employee, "time": punch_time},
#                 ["name", "device_id", "log_type"],
#                 as_dict=True,
#             )

#             if existing:
#                 existing_device_id = existing.device_id or ""

#                 # Only reconcile records owned by this API integration.
#                 if existing_device_id.startswith(API_DEVICE_PREFIX):
#                     if existing.log_type != expected_type:
#                         if not dry_run:
#                             frappe.db.set_value(
#                                 "Employee Checkin",
#                                 existing.name,
#                                 "log_type",
#                                 expected_type,
#                                 update_modified=False,
#                             )
#                         updated_api_log_types += 1
#                     else:
#                         skipped += 1
#                 else:
#                     # Never alter an existing checkin from another source.
#                     skipped += 1

#                 continue

#             if dry_run:
#                 created += 1
#                 continue

#             checkin = frappe.get_doc(
#                 {
#                     "doctype": "Employee Checkin",
#                     "employee": employee,
#                     "time": punch_time,
#                     "log_type": expected_type,
#                     "device_id": api_device_id,
#                 }
#             )
#             checkin.insert(ignore_permissions=True)
#             created += 1

#     if not dry_run:
#         frappe.db.commit()

#     return {
#         "status": "Dry run completed" if dry_run else "Sync completed",
#         "dry_run": dry_run,
#         "date_from": str(start_date),
#         "date_to": str(end_date),
#         "records_read": records_read,
#         "unique_employee_day_groups": len(punches_by_employee_day),
#         "checkins_to_create_or_created": created,
#         "existing_records_skipped": skipped,
#         "api_log_types_to_update_or_updated": updated_api_log_types,
#         "preview": preview[:100],
#         "errors": errors,
#     }



import frappe
from datetime import datetime, time

from frappe.utils import add_days, getdate, nowdate
from team_office_attendance.utils.etimeoffice_api import fetch_punch_data


API_DEVICE_PREFIX = "TEAM_OFFICE_API:"


def _get_api_credentials():
    """Read eTimeOffice credentials from the current site's configuration."""

    corporate_id = frappe.conf.get("etimeoffice_corporate_id")
    username = frappe.conf.get("etimeoffice_username")
    password = frappe.conf.get("etimeoffice_password")

    if not corporate_id or not username or not password:
        raise ValueError(
            "eTimeOffice credentials missing from site configuration."
        )

    return corporate_id, username, password


def _parse_punch_time(value):
    """Convert eTimeOffice punch date/time into a Python datetime."""

    if isinstance(value, datetime):
        return value

    if not value:
        raise ValueError("PunchDate is empty.")

    return datetime.strptime(
        str(value).strip(),
        "%d/%m/%Y %H:%M:%S",
    )


def _get_expected_log_types(punches):
    """
    First punch of the day: IN
    Intermediate punches: blank
    Last punch of the day: OUT
    Single punch: IN
    """

    ordered = sorted(punches, key=lambda item: item["time"])
    count = len(ordered)

    for index, punch in enumerate(ordered):
        if index == 0:
            punch["log_type"] = "IN"
        elif index == count - 1:
            punch["log_type"] = "OUT"
        else:
            punch["log_type"] = ""

    return ordered


def sync_etimeoffice_punches(
    dry_run=True,
    start_date=None,
    end_date=None,
):
    """
    Fetch Team Office punches and optionally create Employee Checkins.

    Default:
        Fetch the latest seven calendar days.

    Historical preview example:
        sync_etimeoffice_punches(
            dry_run=True,
            start_date="2026-01-01",
            end_date="2026-10-26",
        )

    Actual save example:
        sync_etimeoffice_punches(
            dry_run=False,
            start_date="2026-01-01",
            end_date="2026-10-26",
        )

    dry_run=True:
        Preview only. Does not insert, update, or delete records.

    dry_run=False:
        Inserts new records only. Existing records are not updated
        or deleted.
    """

    result = {
        "status": "Starting",
        "dry_run": dry_run,
        "date_from": None,
        "date_to": None,
        "records_read": 0,
        "unique_employee_day_groups": 0,
        "checkins_to_create_or_created": 0,
        "existing_records_skipped": 0,
        "preview": [],
        "errors": [],
    }

    # Credentials
    try:
        corporate_id, username, password = _get_api_credentials()
    except Exception as exc:
        result["status"] = "Failed"
        result["errors"].append(str(exc))
        return result

    # Date range
    try:
        end_date = getdate(end_date) if end_date else getdate(nowdate())

        if start_date:
            start_date = getdate(start_date)
        else:
            start_date = add_days(end_date, -6)

        if start_date > end_date:
            raise ValueError("Start date cannot be after end date.")

    except Exception as exc:
        result["status"] = "Invalid date range"
        result["errors"].append(str(exc))
        return result

    result["date_from"] = str(start_date)
    result["date_to"] = str(end_date)

    # Enabled employee mappings
    mappings = frappe.get_all(
        "Team Office Employee Mapping",
        filters={"enabled": 1},
        fields=[
            "etimeoffice_employee_code",
            "employee",
        ],
        order_by="etimeoffice_employee_code asc",
    )

    if not mappings:
        result["status"] = "No enabled employee mappings"
        return result

    all_punches = []
    errors = []

    # Fetch all mapped employee data before writing anything.
    for mapping in mappings:
        employee_code = mapping.get("etimeoffice_employee_code")
        employee = mapping.get("employee")

        if not employee_code or not employee:
            errors.append(
                f"Mapping has missing employee code or Employee: {mapping}"
            )
            continue

        try:
            api_from_date = (
                f"{start_date.strftime('%d/%m/%Y')}_00:00"
            )
            api_to_date = (
                f"{end_date.strftime('%d/%m/%Y')}_23:59"
            )

            response = fetch_punch_data(
                corporate_id,
                username,
                password,
                employee_code,
                api_from_date,
                api_to_date,
            )

            if not isinstance(response, dict):
                raise ValueError("API response is not a JSON object.")

            if response.get("Error"):
                raise ValueError(
                    str(response.get("Msg") or "API returned an error.")
                )

            punch_data = response.get("PunchData", [])

            if punch_data is None:
                punch_data = []

            if not isinstance(punch_data, list):
                raise ValueError("API PunchData is not a list.")

            for row in punch_data:
                returned_code = str(
                    row.get("Empcode") or ""
                ).strip()

                # Do not assign punches to another employee.
                if returned_code and returned_code != str(employee_code):
                    errors.append(
                        f"Employee code mismatch: requested "
                        f"{employee_code}, received {returned_code}."
                    )
                    continue

                punch_time = _parse_punch_time(row.get("PunchDate"))

                # Restrict records to the requested date range.
                if not (
                    datetime.combine(start_date, time.min)
                    <= punch_time
                    <= datetime.combine(end_date, time.max)
                ):
                    continue

                all_punches.append(
                    {
                        "employee": employee,
                        "employee_code": str(employee_code),
                        "time": punch_time,
                        "api_employee_name": row.get("Name"),
                    }
                )

        except Exception as exc:
            errors.append(
                f"API fetch failed for employee code "
                f"{employee_code}: {exc}"
            )

    result["records_read"] = len(all_punches)

    # If an API/mapping error occurred, do not write any records.
    if errors:
        result["status"] = "Failed - no records written"
        result["errors"] = errors
        return result

    # Deduplicate employee + timestamp within API response.
    unique_punches = {}

    for punch in all_punches:
        key = (punch["employee"], punch["time"])

        if key not in unique_punches:
            unique_punches[key] = punch

    # Group punches by employee and calendar day.
    punches_by_employee_day = {}

    for punch in unique_punches.values():
        day_key = (
            punch["employee"],
            punch["time"].date(),
        )

        punches_by_employee_day.setdefault(
            day_key, []
        ).append(punch)

    result["unique_employee_day_groups"] = len(
        punches_by_employee_day
    )

    # Assign log types to the fetched API punches.
    prepared_punches = []

    for group in punches_by_employee_day.values():
        prepared_punches.extend(
            _get_expected_log_types(group)
        )

    prepared_punches.sort(
        key=lambda item: (
            item["employee"],
            item["time"],
        )
    )

    records_to_create = []

    for punch in prepared_punches:
        punch_time_string = punch["time"].strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # Duplicate protection: same employee and exact timestamp.
        existing = frappe.get_all(
            "Employee Checkin",
            filters={
                "employee": punch["employee"],
                "time": punch_time_string,
            },
            fields=["name"],
            limit=1,
        )

        if existing:
            result["existing_records_skipped"] += 1
            continue

        preview_item = {
            "employee": punch["employee"],
            "employee_code": punch["employee_code"],
            "time": punch_time_string,
            "log_type": punch["log_type"],
        }

        result["preview"].append(preview_item)
        records_to_create.append(punch)

    result["checkins_to_create_or_created"] = len(
        records_to_create
    )

    # Dry run: preview only, without database writes.
    if dry_run:
        result["status"] = "Dry run completed"
        return result

    # Actual mode: insert new records only.
    try:
        for punch in records_to_create:
            checkin = frappe.get_doc(
                {
                    "doctype": "Employee Checkin",
                    "employee": punch["employee"],
                    "time": punch["time"],
                    "log_type": punch["log_type"],
                    "device_id": (
                        API_DEVICE_PREFIX + punch["employee_code"]
                    ),
                }
            )

            checkin.insert(ignore_permissions=True)

        frappe.db.commit()

        result["status"] = "Sync completed"
        return result

    except Exception as exc:
        frappe.db.rollback()
        result["status"] = "Failed - transaction rolled back"
        result["errors"].append(str(exc))
        return result
