"""Add the Visit module to an existing site rail without resetting its arrangement."""

from frappe.desk.doctype.dock.dock import dock_rows, get_dock, save_site_dock


def execute():
    dock = get_dock("wahni_solar")
    if not dock:
        # A fresh site uses the four entries in the app's standard Dock.
        return
    items = dock_rows(dock)
    if any(row.get("link_type") == "Sidebar" and row.get("link_to") == "Site Visits" for row in items):
        return
    position = next(
        (index + 1 for index, row in enumerate(items)
         if row.get("link_type") == "Sidebar" and row.get("link_to") == "Wahni Solar Proposal"),
        len(items),
    )
    items.insert(position, {"link_type": "Sidebar", "link_to": "Site Visits"})
    save_site_dock("wahni_solar", items)
