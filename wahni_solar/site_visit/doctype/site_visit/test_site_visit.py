"""Site-independent regression checks; run with python -m unittest."""

import json
import unittest
from inspect import unwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe

from wahni_solar.site_visit import api
from wahni_solar.site_visit.doctype.site_visit import site_visit
from wahni_solar.wahni_solar_proposal.doctype.solar_proposal import solar_proposal


class Record(frappe._dict):
    def check_permission(self, permission):
        if self.get("denied"):
            raise frappe.PermissionError

    def get_doc_before_save(self):
        return self.get("previous")

    def set(self, field, value):
        self[field] = value

    def is_new(self):
        return not self.get("previous")


class SiteVisitTestCase(unittest.TestCase):
    def setUp(self):
        # Translation caches require an initialized site; these are unit tests.
        for module in (api, site_visit):
            translation = patch.object(module, "_", side_effect=lambda message: message)
            translation.start()
            self.addCleanup(translation.stop)
        eligible = patch.object(site_visit, "is_eligible_supervisor", return_value=True)
        eligible.start()
        self.addCleanup(eligible.stop)


class TestSiteVisit(SiteVisitTestCase):
    def record(self, **values):
        return Record({"solar_proposal": "P", "status": "Assigned", "site_visit_by": "EMP",
                       "visit_date": None, "loan_percentage": 0, **values})

    def test_completion_requires_a_date_and_supervisor(self):
        for values in ({"site_visit_by": None}, {"visit_date": "2026-11-13", "site_visit_by": None}, {"site_visit_by": "EMP"}):
            with self.subTest(values=values), patch.object(site_visit, "frappe") as fake:
                fake.throw.side_effect = ValueError
                with self.assertRaises(ValueError):
                    site_visit.SiteVisit.validate(self.record(status="Completed", **values))
                fake.only_for.assert_called_once_with(("System Manager", "Project Supervisor"))

    def test_completion_validates_supervisor_again(self):
        previous = self.record(site_visit_by="EMP")
        doc = self.record(previous=previous, status="Completed", site_visit_by="EMP", visit_date="2026-11-13")
        with patch.object(site_visit, "frappe") as fake, \
                patch.object(site_visit, "is_eligible_supervisor", return_value=False) as eligible:
            fake.throw.side_effect = ValueError
            with self.assertRaises(ValueError):
                site_visit.SiteVisit.validate(doc)
            eligible.assert_called_once_with("EMP")

    def test_historical_assignment_can_be_saved_after_employee_leaves(self):
        previous = self.record(status="Completed", site_visit_by="EMP")
        doc = self.record(previous=previous, status="Completed", site_visit_by="EMP", visit_date="2026-11-13")
        with patch.object(site_visit, "is_eligible_supervisor") as eligible:
            site_visit.SiteVisit.validate(doc)
            eligible.assert_not_called()

    def test_completed_report_cannot_lose_its_date_or_supervisor(self):
        previous = self.record(status="Completed", site_visit_by="EMP", visit_date="2026-11-13")
        for values in ({"visit_date": None}, {"site_visit_by": None}):
            doc = self.record(previous=previous, status="Completed", site_visit_by="EMP", visit_date="2026-11-13")
            doc.update(values)
            with self.subTest(values=values), patch.object(site_visit, "frappe") as fake:
                fake.throw.side_effect = ValueError
                with self.assertRaises(ValueError):
                    site_visit.SiteVisit.validate(doc)

    def test_new_assignment_requires_eligible_employee(self):
        with patch.object(site_visit, "frappe") as fake, \
                patch.object(site_visit, "is_eligible_supervisor", return_value=False):
            fake.throw.side_effect = ValueError
            with self.assertRaises(ValueError):
                site_visit.SiteVisit.validate(self.record(site_visit_by="EMP"))

    def test_assignment_can_be_saved_without_visit_details(self):
        for status in ("Assigned", "In Progress"):
            with self.subTest(status=status):
                site_visit.SiteVisit.validate(self.record(status=status))

    def test_new_assignment_requires_employee(self):
        with patch.object(site_visit, "frappe") as fake:
            fake.throw.side_effect = ValueError
            with self.assertRaises(ValueError):
                site_visit.SiteVisit.validate(self.record(site_visit_by=None))

    def test_existing_unassigned_report_can_be_saved(self):
        previous = self.record(site_visit_by=None)
        site_visit.SiteVisit.validate(self.record(previous=previous, site_visit_by=None))

    def test_draft_and_unknown_status_are_rejected(self):
        for status in ("Draft", "Other", None):
            with self.subTest(status=status), patch.object(site_visit, "frappe") as fake:
                fake.throw.side_effect = ValueError
                with self.assertRaises(ValueError):
                    site_visit.SiteVisit.validate(self.record(status=status))

    def test_proposal_cannot_be_changed(self):
        with patch.object(site_visit, "frappe") as fake:
            fake.throw.side_effect = ValueError
            with self.assertRaises(ValueError):
                site_visit.SiteVisit.validate(self.record(solar_proposal="OTHER", previous=self.record()))

    def test_loan_percentage_range(self):
        for percentage in (-1, 101):
            with self.subTest(percentage=percentage), patch.object(site_visit, "frappe") as fake:
                fake.throw.side_effect = ValueError
                with self.assertRaises(ValueError):
                    site_visit.SiteVisit.validate(self.record(loan_percentage=percentage))
        for percentage in (0, 100):
            site_visit.SiteVisit.validate(self.record(loan_percentage=percentage))

    def test_drawing_must_be_a_private_readable_file(self):
        with patch.object(site_visit, "frappe") as fake:
            fake.throw.side_effect = ValueError
            fake.db.get_value.return_value = None
            with self.assertRaises(ValueError):
                site_visit.SiteVisit.validate(self.record(panel_layout="/files/public.pdf"))
            fake.db.get_value.return_value = "FILE"
            site_visit.SiteVisit.validate(self.record(panel_layout="/private/files/layout.pdf"))
            fake.get_doc.return_value.check_permission.assert_called_once_with("read")

    def test_defaults_only_fill_new_report_and_preserve_manual_edits(self):
        doc = self.record(customer_name="Manual name", requested_capacity_kw=0)
        with patch.object(site_visit.frappe, "get_doc"), \
                patch.object(site_visit, "proposal_defaults", return_value={"customer_name": "Source", "requested_capacity_kw": 5}) as defaults:
            site_visit.SiteVisit.before_validate(doc)
            self.assertEqual(doc.customer_name, "Manual name")
            self.assertEqual(doc.requested_capacity_kw, 5)
            doc.previous = self.record()
            site_visit.SiteVisit.before_validate(doc)
            defaults.assert_called_once()

    def test_schema_has_unique_proposal_and_complete_field_order(self):
        schema = json.loads(Path(__file__).with_name("site_visit.json").read_text())
        fields = {field["fieldname"]: field for field in schema["fields"]}
        self.assertEqual(set(schema["field_order"]), set(fields))
        self.assertEqual(len(schema["field_order"]), len(fields))
        self.assertEqual(fields["solar_proposal"]["unique"], 1)
        self.assertEqual(fields["status"]["permlevel"], 1)
        self.assertEqual(fields["status"]["default"], "Assigned")
        self.assertEqual(fields["status"]["options"], "Assigned\nIn Progress\nCompleted")
        self.assertEqual(fields["visit_date"]["mandatory_depends_on"], "eval:doc.status == 'Completed'")
        for drawing in api.DRAWING_FIELDS:
            self.assertEqual(fields[drawing]["fieldtype"], "Attach")


class TestSiteVisitAPI(SiteVisitTestCase):
    def proposal(self, **values):
        return Record({"doctype": "Solar Proposal", "name": "P", "proposal_to": "Lead", "party": "L",
                       "company": "COMPANY", "currency": "INR", "customer_name": "Customer", "capacity_kw": 5, **values})

    def test_lead_defaults_include_kseb_and_contact_data(self):
        lead = Record(doctype="Lead", name="L", mobile_no="9000000000", email_id="lead@example.com",
                      lead_owner="sales@example.com", source="Campaign", custom_kseb_consumer_no="001234",
                      custom_kseb_connected_mobile_no="9111111111")
        with patch.object(api, "frappe") as fake, patch.object(api, "get_default_contact", return_value=None), \
                patch.object(api, "get_default_address", return_value=None):
            fake.get_doc.return_value = lead
            fake.db.get_value.return_value = "C"
            values = api.proposal_defaults(self.proposal())
        self.assertEqual((values["lead"], values["customer"]), ("L", "C"))
        self.assertEqual(values["consumer_number"], "001234")
        self.assertEqual(values["lead_source"], "Campaign")
        self.assertEqual(values["requested_capacity_kw"], 5)
        self.assertEqual(values["contact_number"], "9000000000")

    def test_customer_defaults_resolve_originating_lead_contact_and_address(self):
        docs = {
            ("Customer", "C"): Record(doctype="Customer", name="C", lead_name="L", customer_primary_contact="CT", customer_primary_address="A"),
            ("Lead", "L"): Record(name="L", lead_owner="sales@example.com"),
            ("Contact", "CT"): Record(mobile_no="9000000000", email_id="customer@example.com"),
            ("Address", "A"): Record(address_line1="Site road", city="Thrissur", pincode="001234"),
        }
        with patch.object(api, "frappe") as fake:
            fake.get_doc.side_effect = lambda *args: docs[args]
            values = api.proposal_defaults(self.proposal(proposal_to="Customer", party="C"))
        self.assertEqual((values["lead"], values["customer"]), ("L", "C"))
        self.assertEqual(values["contact_number"], "9000000000")
        self.assertEqual(values["address"], "Site road\nThrissur\n001234")
        self.assertEqual(values["pincode"], "001234")

    def test_prospect_is_supported_without_lead_or_customer(self):
        with patch.object(api, "frappe") as fake, patch.object(api, "get_default_contact", return_value=None), \
                patch.object(api, "get_default_address", return_value=None):
            fake.get_doc.return_value = Record(doctype="Prospect", name="PR")
            values = api.proposal_defaults(self.proposal(proposal_to="Prospect", party="PR"))
        self.assertNotIn("lead", values)
        self.assertNotIn("customer", values)

    def test_autofill_requires_source_proposal_access(self):
        with self.assertRaises(frappe.PermissionError):
            api.proposal_defaults(self.proposal(denied=True))

    def test_existing_visit_is_opened_instead_of_creating_a_duplicate(self):
        visit = MagicMock()
        with patch.object(api, "frappe") as fake, patch.object(api, "get_proposal_visit", return_value=Record(name="SV")):
            fake.get_doc.side_effect = [self.proposal(), visit]
            self.assertIs(unwrap(api.make_site_visit)("P"), visit)
            visit.check_permission.assert_called_once_with("read")
            fake.new_doc.assert_not_called()
            visit.save.assert_not_called()

    def test_new_visit_is_an_unsaved_snapshot(self):
        with patch.object(api, "frappe") as fake, patch.object(api, "get_proposal_visit", return_value=None), \
                patch.object(api, "proposal_defaults", return_value={"solar_proposal": "P"}):
            fake.get_doc.return_value = self.proposal()
            visit = unwrap(api.make_site_visit)("P")
            visit.check_permission.assert_called_once_with("create")
            visit.update.assert_called_once_with({"solar_proposal": "P"})
            visit.insert.assert_not_called()
            visit.save.assert_not_called()

    def test_supervisor_requires_active_employee_enabled_user_and_role(self):
        cases = [(None, 1, 0, [api.SUPERVISOR_ROLE], False),
                 ("USER", 0, 0, [api.SUPERVISOR_ROLE], False),
                 ("USER", 1, 1, [api.SUPERVISOR_ROLE], False),
                 ("USER", 1, 0, [], False),
                 ("USER", 1, 0, [api.SUPERVISOR_ROLE], True)]
        for user, enabled, disabled_role, roles, expected in cases:
            with self.subTest(user=user, enabled=enabled, roles=roles), patch.object(api, "frappe") as fake:
                fake.db.get_value.side_effect = [user, enabled, disabled_role]
                fake.get_roles.return_value = roles
                self.assertEqual(api.is_eligible_supervisor("EMP"), expected)
                self.assertEqual(fake.db.get_value.call_args_list[0].args,
                                 ("Employee", {"name": "EMP", "status": "Active"}, "user_id"))

    def test_supervisor_search_requires_site_visit_access(self):
        with patch.object(api, "frappe") as fake:
            fake.has_permission.return_value = False
            fake.throw.side_effect = frappe.PermissionError
            with self.assertRaises(frappe.PermissionError):
                unwrap(api.supervisor_query)("Employee", "", "name", 0, 20, {})
            fake.qb.from_.assert_not_called()


class TestProjectSiteVisit(SiteVisitTestCase):
    def test_missing_visit_warns_but_does_not_block(self):
        doc = Record(custom_solar_proposal="P")
        with patch.object(api, "get_proposal_visit", return_value=None), patch.object(api.frappe, "msgprint") as warn:
            api.validate_project_site_visit(doc)
            warn.assert_called_once()
            self.assertFalse(doc.custom_site_visit)

    def test_incomplete_visit_is_linked_with_warning_completed_without_warning(self):
        for status in ("Assigned", "In Progress", "Completed"):
            doc = Record(custom_solar_proposal="P")
            visit = Record(name="SV", solar_proposal="P", status=status)
            with self.subTest(status=status), patch.object(api, "get_proposal_visit", return_value=visit), \
                    patch.object(api.frappe, "msgprint") as warn:
                api.validate_project_site_visit(doc)
                self.assertEqual(doc.custom_site_visit, "SV")
                self.assertEqual(warn.call_count, int(status != "Completed"))

    def test_cross_proposal_or_nonexistent_visit_is_rejected(self):
        for proposal in ("P", None):
            for visit in (None, Record(name="SV", solar_proposal="OTHER")):
                with self.subTest(proposal=proposal, visit=visit), patch.object(api, "frappe") as fake:
                    fake.db.get_value.return_value = visit
                    fake.throw.side_effect = ValueError
                    with self.assertRaises(ValueError):
                        api.validate_project_site_visit(Record(custom_solar_proposal=proposal, custom_site_visit="SV"))

    def test_unrelated_project_is_unchanged(self):
        with patch.object(api, "get_proposal_visit") as find, patch.object(api.frappe, "msgprint") as warn:
            api.validate_project_site_visit(Record())
            find.assert_not_called()
            warn.assert_not_called()

    def test_later_visit_is_linked_on_next_save_without_repeated_warnings(self):
        previous = Record(custom_solar_proposal="P")
        doc = Record(custom_solar_proposal="P", previous=previous)
        visit = Record(name="SV", solar_proposal="P", status="In Progress")
        with patch.object(api, "frappe") as fake, patch.object(api, "get_proposal_visit", return_value=visit):
            fake.db.get_value.return_value = visit
            api.validate_project_site_visit(doc)
            self.assertEqual(doc.custom_site_visit, "SV")
            self.assertEqual(fake.msgprint.call_count, 1)
            doc.previous = Record(custom_solar_proposal="P", custom_site_visit="SV")
            api.validate_project_site_visit(doc)
            self.assertEqual(fake.msgprint.call_count, 1)

    def test_mapping_retains_customer_bom_cost_plan_and_does_not_save_relationships(self):
        for status in (None, "Assigned", "Completed"):
            proposal = MagicMock()
            proposal.name = "P"
            proposal.package_name = "PACKAGE"
            target = Record()
            visit = Record(name="SV", status=status) if status else None

            def map_doc(source_type, source_name, mapping, target_doc, postprocess):
                self.assertIn("Solar Proposal BOM Item", mapping)
                self.assertIn("Project Cost Breakdown", mapping)
                postprocess(proposal, target)
                return target

            with self.subTest(status=status), patch.object(solar_proposal, "frappe") as fake, \
                    patch.object(solar_proposal, "get_customer", return_value="CUSTOMER"), \
                    patch.object(solar_proposal, "get_proposal_visit", return_value=visit), \
                    patch.object(solar_proposal, "warn_incomplete_visit") as warn, \
                    patch.object(solar_proposal, "get_mapped_doc", side_effect=map_doc):
                fake.get_doc.return_value = proposal
                fake.db.get_value.return_value = ("Customer", "CUSTOMER")
                result = unwrap(solar_proposal.make_project)("P")
                self.assertEqual(result.customer, "CUSTOMER")
                self.assertEqual(result.custom_solar_proposal, "P")
                self.assertEqual(result.custom_site_visit, "SV" if visit else None)
                proposal.before_print.assert_called_once()
                warn.assert_called_once_with(visit)
                fake.db.set_value.assert_not_called()
                proposal.save.assert_not_called()
