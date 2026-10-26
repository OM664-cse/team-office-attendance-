import frappe
from frappe.model.document import Document


class TeamOfficeMachineSettings(Document):
    def validate(self):
        if self.port and not (1 <= int(self.port) <= 65535):
            frappe.throw("Port must be between 1 and 65535.")
