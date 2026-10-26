# Copyright (c) 2026, mujeebcpy and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from wahni_solar.wahni_solar_proposal.doctype.solar_package.solar_package import (
    validate_formula,
    validate_key,
)


class SolarComponentTemplate(Document):
    def validate(self):
        keys = set()
        for row in self.items or []:
            validate_key(row.rule_key, keys, f"Material row {row.idx} rule key")
            validate_formula(row.include_when, f"Material row {row.idx} Include When")
            validate_formula(row.quantity_formula, f"Material row {row.idx} Quantity Formula")
            if row.enabled and not (row.quantity_formula or "").strip():
                frappe.throw(f"Material row {row.idx}: enter a Quantity Formula.")

            if row.item_code and (not row.uom or not row.description):
                defaults = frappe.db.get_value("Item", row.item_code, ["stock_uom", "description"], as_dict=True)
                if defaults:
                    row.uom = row.uom or defaults.stock_uom
                    row.description = row.description or defaults.description

        # Variable names depend on whichever package uses this reusable template.
        # The package preview checks names and cross-template quantity references.
        validate_formula(self.validation_condition, "Validation Condition")
