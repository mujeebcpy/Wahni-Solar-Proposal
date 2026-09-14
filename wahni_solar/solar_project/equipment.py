"""Item equipment details and the Solar Package brand lookup."""

import frappe
from frappe.utils import cint


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def microinverter_brand_query(doctype, txt, searchfield, start, page_len, filters):
    brands = frappe.get_list(
        "Item",
        filters={"item_group": "Microinverters", "disabled": 0, "brand": ["is", "set"]},
        pluck="brand", group_by="brand", limit_page_length=0,
    )
    if not brands:
        return []
    return frappe.get_list(
        "Brand", filters={"name": ["in", brands], "brand": ["like", f"%{txt or ''}%"]},
        fields=["name"], order_by="name asc", start=cint(start),
        page_length=cint(page_len), as_list=True,
    )


def migrate_package_brands():
    """Preserve existing Select values when Solar Package.brand becomes a Link."""
    for brand in frappe.get_all("Solar Package", filters={"brand": ["is", "set"]},
                                pluck="brand", group_by="brand"):
        if not frappe.db.exists("Brand", brand):
            frappe.get_doc({"doctype": "Brand", "brand": brand}).insert(ignore_permissions=True)
