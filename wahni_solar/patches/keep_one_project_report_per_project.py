"""One-time cleanup: keep only the latest Project Report for each Project.

Generation now updates a single Project Report per Project, and the Project link
becomes unique, so older duplicates are removed before the DocType is synced.

Temporary: delete this file and its patches.txt line once it has run on every site.
"""

import frappe


def execute():
    if not frappe.db.table_exists("Project Report"):
        return
    keep = {}
    for row in frappe.db.sql("SELECT name, project, status FROM `tabProject Report` ORDER BY creation DESC, name DESC",
                             as_dict=True):
        if row.project and row.project not in keep:
            keep[row.project] = row
    kept = {row.name for row in keep.values()}
    remove = [name for name in frappe.db.sql_list("SELECT name FROM `tabProject Report`") if name not in kept]
    if remove:
        # Delete File records through the controller so stored files go too.
        for name in frappe.get_all("File", filters={"attached_to_doctype": "Project Report",
                                                    "attached_to_name": ["in", remove]}, pluck="name"):
            frappe.delete_doc("File", name, ignore_permissions=True, force=True)
        frappe.db.delete("Version", {"ref_doctype": "Project Report", "docname": ["in", remove]})
        frappe.db.delete("Comment", {"reference_doctype": "Project Report", "reference_name": ["in", remove]})
        frappe.db.delete("Project Report", {"name": ["in", remove]})
    for project, report in keep.items():
        frappe.db.set_value("Project", project, {"custom_latest_project_report": report.name,
                                                 "custom_project_report_status": report.status}, update_modified=False)
    print(f"Kept {len(keep)} Project Reports; removed {len(remove)} older duplicates.")
