import unittest
from unittest.mock import call, patch

import frappe

from wahni_solar.site_visit import migrate_visit_status
from wahni_solar.site_visit.doctype.pms_visit.pms_visit import COMPLETION_FIELDS


class TestVisitStatusMigration(unittest.TestCase):
    def test_migration_preserves_complete_history_and_incomplete_assignments(self):
        complete = {field: "Present" for field in COMPLETION_FIELDS}
        visits = [
            frappe._dict(name="COMPLETE", status="Assigned", **complete),
            frappe._dict(name="PARTIAL", status="Assigned"),
            frappe._dict(name="EMPTY", status=None),
            frappe._dict(name="ACTIVE", status="In Progress", **complete),
            frappe._dict(name="HISTORY", status="Completed", **complete),
        ]
        with patch.object(migrate_visit_status, "frappe") as fake:
            fake.get_all.return_value = visits
            migrate_visit_status.execute()
            self.assertEqual(fake.db.set_value.call_args_list, [
                call("Site Visit", {"status": "Draft"}, "status", "Assigned", update_modified=False),
                call("PMS Visit", "COMPLETE", "status", "Completed", update_modified=False),
                call("PMS Visit", "EMPTY", "status", "Assigned", update_modified=False),
            ])

    def test_migration_is_idempotent(self):
        visits = [frappe._dict(name="DONE", status="Completed"), frappe._dict(name="PARTIAL", status="Assigned")]
        with patch.object(migrate_visit_status, "frappe") as fake:
            fake.get_all.return_value = visits
            migrate_visit_status.execute()
            fake.db.set_value.assert_called_once_with(
                "Site Visit", {"status": "Draft"}, "status", "Assigned", update_modified=False
            )
