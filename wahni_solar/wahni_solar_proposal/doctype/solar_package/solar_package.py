# Copyright (c) 2026, mujeebcpy and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SolarPackage(Document):
    def validate(self):
        previous = self.get_doc_before_save()
        # Existing packages remain editable while their Item masters are populated.
        if previous and previous.brand == self.brand:
            return
        if self.brand and not frappe.db.exists(
            "Item", {"item_group": "Microinverters", "disabled": 0, "brand": self.brand}
        ):
            frappe.throw(
                "Choose a brand used by an enabled Item in the Microinverters item group. "
                "Set the Brand on that Item first."
            )
