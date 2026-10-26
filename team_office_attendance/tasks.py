import frappe


def sync_etimeoffice_punches_scheduled():
    """Automatically sync Team Office face attendance every 5 minutes."""

    from team_office_attendance.utils.attendance_sync import (
        sync_etimeoffice_punches,
    )

    try:
        result = sync_etimeoffice_punches(dry_run=False)

        if result.get("errors") or result.get("status") != "Sync completed":
            frappe.log_error(
                title="Team Office Attendance Sync Issue",
                message=frappe.as_json(result),
            )

        return result

    except Exception:
        frappe.log_error(
            title="Team Office Attendance Sync Failed",
            message=frappe.get_traceback(),
        )
        raise
