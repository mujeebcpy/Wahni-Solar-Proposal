"""Wahni Field expense claims against installed HRMS; test records are rolled back.

bench --site <site> execute wahni_solar.field_portal.tests.test_expenses_integration.run
"""

import unittest

import frappe
from frappe.utils import add_days, nowdate
from frappe.utils.file_manager import save_file

from wahni_solar.field_portal import expenses
from wahni_solar.field_portal.tests.test_access_integration import TestFieldAccess


class TestFieldExpenses(TestFieldAccess):
    def setUp(self):
        super().setUp()
        if "hrms" not in frappe.get_installed_apps():
            self.skipTest("HRMS is not installed")
        self.approver = self.user("Expense Approver").name
        self.expense_type = self.fixture("Expense Claim Type", expense_type=f"Field Test {self.token}")
        account = frappe.db.get_value("Account", {"company": self.company, "is_group": 0, "root_type": "Expense"})
        self.assertTrue(account, "The test company needs an expense account")
        self.fixture("Expense Claim Account", parent=self.expense_type.name, parenttype="Expense Claim Type",
                     parentfield="accounts", company=self.company, default_account=account)

    def claimant(self):
        user, employee = self.field_user()
        frappe.db.set_value("Employee", employee, "expense_approver", self.approver)
        # HRMS scopes Employee-role users to their own records with this permission
        # (created automatically for real employees; fixtures bypass the controller).
        frappe.get_doc({"doctype": "User Permission", "user": user, "allow": "Employee", "for_value": employee,
                        "apply_to_all_doctypes": 1}).insert(ignore_permissions=True)
        return user, employee

    def values(self, **extra):
        return {
            "posting_date": nowdate(), "expense_approver": self.approver,
            "expenses": [
                {"expense_date": nowdate(), "expense_type": self.expense_type.name, "description": "Bus <b>fare</b>", "amount": 120.5},
                {"expense_date": add_days(nowdate(), -1), "expense_type": self.expense_type.name, "description": "Lunch", "amount": 80},
            ],
            **extra,
        }

    def test_form_options(self):
        user, employee = self.claimant()
        frappe.set_user(user)
        options = expenses.get_form_options()
        self.assertEqual(options["employee"]["name"], employee)
        self.assertEqual([a["value"] for a in options["approvers"]], [self.approver])
        self.assertIn(self.expense_type.name, [t.name for t in options["expense_types"]])

    def test_draft_uses_session_employee_and_server_totals(self):
        user, employee = self.claimant()
        _other_user, other_employee = self.claimant()
        frappe.set_user(user)
        claim = expenses.save_claim(self.values(employee=other_employee, total_claimed_amount=1, approval_status="Approved"))
        self.assertEqual(claim["employee"], employee)
        self.assertEqual(claim["docstatus"], 0)
        self.assertEqual(claim["approval_status"], "Draft")
        self.assertEqual(claim["total_claimed_amount"], 200.5)
        self.assertNotIn("<b>", frappe.db.get_value("Expense Claim Detail", {"parent": claim["name"], "idx": 1}, "description"))
        self.assertTrue(claim["editable"])
        self.assertEqual(claim["actions"], [])
        self.assertIn(claim["name"], [row.name for row in expenses.list_claims()])
        self.assertIn(claim["name"], [row.name for row in expenses.list_claims(status="draft")])
        self.assertNotIn(claim["name"], [row.name for row in expenses.list_claims(status="paid")])

    def test_retry_with_same_token_does_not_duplicate(self):
        user, _employee = self.claimant()
        frappe.set_user(user)
        first = expenses.save_claim(self.values(), client_token=f"tok-{self.token}")
        second = expenses.save_claim(self.values(), client_token=f"tok-{self.token}")
        self.assertEqual(first["name"], second["name"])

    def test_update_detects_concurrent_edit(self):
        user, _employee = self.claimant()
        frappe.set_user(user)
        claim = expenses.save_claim(self.values())
        stale = claim["modified"]
        updated = expenses.save_claim({**self.values(), "name": claim["name"], "modified": stale,
                                       "expenses": [{"expense_type": self.expense_type.name, "amount": 50}]})
        self.assertEqual(updated["total_claimed_amount"], 50)
        frappe.db.set_value("Expense Claim", claim["name"], "modified", add_days(updated["modified"], 1), update_modified=False)
        with self.assertRaises(frappe.TimestampMismatchError):
            expenses.save_claim({**self.values(), "name": claim["name"], "modified": updated["modified"]})

    def test_other_employees_claims_are_hidden(self):
        user, _employee = self.claimant()
        other_user, _other = self.claimant()
        frappe.set_user(other_user)
        theirs = expenses.save_claim(self.values())
        frappe.set_user(user)
        self.assertNotIn(theirs["name"], [row.name for row in expenses.list_claims()])
        # Even an approver who can read the claim in Desk only sees own claims in the portal.
        with self.assertRaises(frappe.PermissionError):
            expenses.get_claim(theirs["name"])
        with self.assertRaises(frappe.PermissionError):
            expenses.save_claim({**self.values(), "name": theirs["name"]})

    def test_approver_rules(self):
        user, employee = self.claimant()
        frappe.set_user(user)
        with self.assertRaises(frappe.ValidationError):
            expenses.save_claim(self.values(expense_approver=self.user("Expense Approver").name))
        if expenses.approver_required():
            with self.assertRaises(frappe.ValidationError):
                expenses.save_claim(self.values(expense_approver=None))
        with self.assertRaises(frappe.ValidationError):
            expenses.save_claim(self.values(expenses=[]))

    def test_receipts_follow_claim_access(self):
        user, _employee = self.claimant()
        other_user, _other = self.claimant()
        frappe.set_user(user)
        claim = expenses.save_claim(self.values())
        receipt = save_file(f"receipt-{self.token}.txt", b"receipt", "Expense Claim", claim["name"], is_private=1)
        self.assertEqual([r.name for r in expenses.get_claim(claim["name"])["receipts"]], [receipt.name])
        frappe.set_user(other_user)
        other_claim = expenses.save_claim(self.values())
        self.assertFalse(frappe.get_doc("File", receipt.name).has_permission("read"))
        with self.assertRaises(frappe.PermissionError):
            expenses.remove_receipt(other_claim["name"], receipt.name)
        frappe.set_user(user)
        self.assertEqual(expenses.remove_receipt(claim["name"], receipt.name)["receipts"], [])
        self.assertFalse(frappe.db.exists("File", receipt.name))

    def test_submitted_claim_is_read_only(self):
        user, _employee = self.claimant()
        frappe.set_user(user)
        claim = expenses.save_claim(self.values())
        frappe.db.set_value("Expense Claim", claim["name"], {"docstatus": 1, "approval_status": "Approved"})
        payload = expenses.get_claim(claim["name"])
        self.assertFalse(payload["editable"])
        with self.assertRaises(frappe.ValidationError):
            expenses.save_claim({**self.values(), "name": claim["name"], "modified": payload["modified"]})
        self.assertIn(claim["name"], [row.name for row in expenses.list_claims(status="approved")])

    def test_project_search_is_permission_filtered(self):
        user, _employee = self.claimant()
        open_project = self.fixture("Project", project_name=f"Field Open {self.token}", company=self.company, status="Open")
        done = self.fixture("Project", project_name=f"Field Done {self.token}", company=self.company, status="Completed")
        frappe.set_user(user)
        names = [p.name for p in expenses.search_projects(self.token)]
        self.assertIn(open_project.name, names)
        self.assertNotIn(done.name, names)
        frappe.set_user(self.user("Project Supervisor").name)  # no Employee role: no Project access
        with self.assertRaises(frappe.PermissionError):
            expenses.search_projects(self.token)


def run():
    names = sorted(name for name in vars(TestFieldExpenses) if name.startswith("test_"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(TestFieldExpenses(name) for name in names))
    if not result.wasSuccessful():
        raise AssertionError("Field expense integration checks failed")
    return {"passed": result.testsRun, "site": frappe.local.site, "test_records": "rolled back"}
