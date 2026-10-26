"""Legacy cleanup preserves business references and deletes only archived candidates."""

import copy
import json
import stat
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from wahni_solar.wahni_solar_proposal import legacy_cleanup


class Record(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            return None

    def as_dict(self):
        return copy.deepcopy(dict(self))


def record(doctype, name, **values):
    return Record(doctype=doctype, name=name, **values)


class FakeDatabase:
    """A small record store: filters must match real reference values."""

    def __init__(self, rows=None, metas=None):
        self.rows = copy.deepcopy(rows or {})
        self.metas = metas or {}
        self.frappe = MagicMock()
        self.frappe.LinkExistsError = type("LinkExistsError", (Exception,), {})
        self.frappe.get_all.side_effect = self.get_all
        self.frappe.db.get_values.side_effect = self.get_values
        self.frappe.db.get_all.side_effect = self.get_all
        self.frappe.db.exists.side_effect = self.exists
        self.frappe.db.table_exists.return_value = True
        self.frappe.db.has_column.return_value = True
        self.frappe.get_meta.side_effect = self.meta
        self.frappe.get_doc.side_effect = self.get_doc
        self.frappe.db.get_single_value.side_effect = self.get_single_value
        self.frappe.db.get_singles_dict.side_effect = lambda dt: self.rows.get(dt, [{}])[0]
        self.frappe.delete_doc.side_effect = self.delete

    def meta(self, doctype):
        return SimpleNamespace(**{"istable": False, "issingle": False, "is_virtual": False,
                                  **self.metas.get(doctype, {})})

    def matches(self, row, filters):
        for field, value in (filters or {}).items():
            actual = row.get(field)
            if isinstance(value, (list, tuple)):
                operator, expected = value
                if operator == "in" and actual not in expected:
                    return False
                if operator == "!=" and actual == expected:
                    return False
                if operator == "=" and actual != expected:
                    return False
            elif actual != value:
                return False
        return True

    def get_all(self, doctype, filters=None, fields=None, **kwargs):
        rows = [Record(row) for row in self.rows.get(doctype, []) if self.matches(row, filters)]
        if kwargs.get("pluck"):
            return [row.get(kwargs["pluck"]) for row in rows]
        return rows

    def get_values(self, doctype, filters=None, fieldname=None, **kwargs):
        rows = self.get_all(doctype, filters)
        if kwargs.get("as_dict"):
            return rows
        fields = fieldname if isinstance(fieldname, (list, tuple)) else [fieldname or "name"]
        return [[row.get(field) for field in fields] for row in rows]

    def exists(self, doctype, filters):
        filters = filters if isinstance(filters, dict) else {"name": filters}
        return next((row["name"] for row in self.rows.get(doctype, []) if self.matches(row, filters)), None)

    def get_single_value(self, doctype, fieldname):
        return self.rows.get(doctype, [{}])[0].get(fieldname)

    def get_doc(self, doctype, name):
        return next(Record(row) for row in self.rows.get(doctype, []) if row["name"] == name)

    def delete(self, doctype, name, **kwargs):
        self.rows[doctype] = [row for row in self.rows.get(doctype, []) if row["name"] != name]


class TestLegacyDependencies(unittest.TestCase):
    def inspect(self, store, static=None, dynamic=None, doc=None):
        with patch.object(legacy_cleanup, "frappe", store.frappe), \
                patch.object(legacy_cleanup, "get_link_fields", return_value=static or []), \
                patch.object(legacy_cleanup, "get_dynamic_links", return_value=dynamic or []):
            return legacy_cleanup.dependencies(doc or record("Solar Proposal", "PROP"))

    def test_static_projects_block_deletion_in_every_status(self):
        store = FakeDatabase({"Project": [record("Project", "LIVE", custom_solar_proposal="PROP", docstatus=0),
                                           record("Project", "CANCELLED", custom_solar_proposal="PROP", docstatus=2)]})
        references = self.inspect(store, static=[{"parent": "Project", "fieldname": "custom_solar_proposal", "issingle": 0}])
        self.assertEqual({(ref["doctype"], ref["name"]) for ref in references},
                         {("Project", "LIVE"), ("Project", "CANCELLED")})

    def test_cancelled_quotation_child_dynamic_reference_blocks_deletion(self):
        store = FakeDatabase({"Quotation Item": [record("Quotation Item", "Q-ROW", parent="CANCELLED-QUOTE",
                                parenttype="Quotation", parentfield="items", docstatus=2,
                                prevdoc_doctype="Solar Proposal", prevdoc_docname="PROP")]},
                             {"Quotation Item": {"istable": True}})
        references = self.inspect(store, dynamic=[Record(parent="Quotation Item", fieldname="prevdoc_docname", options="prevdoc_doctype")])
        self.assertEqual(references, [{"doctype": "Quotation", "name": "CANCELLED-QUOTE"}])

    def test_same_customer_sales_are_not_dependencies_without_a_document_reference(self):
        store = FakeDatabase({"Sales Order": [record("Sales Order", "UNRELATED", customer="SAME-CUSTOMER",
                               custom_solar_proposal="OTHER", docstatus=1)],
                              "Quotation Item": [record("Quotation Item", "OTHER-ROW", parent="OTHER-QUOTE",
                               parenttype="Quotation", prevdoc_doctype="Lead", prevdoc_docname="PROP")]},
                             {"Quotation Item": {"istable": True}})
        references = self.inspect(store,
            static=[{"parent": "Sales Order", "fieldname": "custom_solar_proposal", "issingle": 0}],
            dynamic=[Record(parent="Quotation Item", fieldname="prevdoc_docname", options="prevdoc_doctype")],
            doc=record("Solar Proposal", "PROP", party="SAME-CUSTOMER"))
        self.assertEqual(references, [])

    def test_housekeeping_references_do_not_block_cleanup(self):
        store = FakeDatabase({"Communication": [record("Communication", "EMAIL", reference_doctype="Solar Proposal", reference_name="PROP")],
                              "Version": [record("Version", "CHANGE", ref_doctype="Solar Proposal", docname="PROP")]})
        references = self.inspect(store, dynamic=[
            Record(parent="Communication", fieldname="reference_name", options="reference_doctype"),
            Record(parent="Version", fieldname="docname", options="ref_doctype")])
        self.assertEqual(references, [])

    def test_self_owned_children_are_not_external_dependencies(self):
        store = FakeDatabase({"Proposal Reference": [record("Proposal Reference", "OWN-ROW", parent="PROP",
                               parenttype="Solar Proposal", proposal="PROP", reference_type="Solar Proposal", reference_name="PROP")]},
                             {"Proposal Reference": {"istable": True}})
        references = self.inspect(store,
            static=[{"parent": "Proposal Reference", "fieldname": "proposal", "issingle": 0}],
            dynamic=[Record(parent="Proposal Reference", fieldname="reference_name", options="reference_type")])
        self.assertEqual(references, [])

    def test_attachments_are_preserved_even_without_a_link_field(self):
        store = FakeDatabase({"File": [record("File", "UPLOADED-DRAWING", attached_to_doctype="Solar Proposal", attached_to_name="PROP"),
                                       record("File", "UNRELATED", attached_to_doctype="Customer", attached_to_name="PROP")]})
        self.assertEqual(self.inspect(store), [{"doctype": "File", "name": "UPLOADED-DRAWING"}])

    def test_singleton_dynamic_references_are_checked_without_the_cached_link_map(self):
        store = FakeDatabase({"Business Settings": [{"reference_type": "Solar Proposal", "reference_name": "PROP"}]},
                             {"Business Settings": {"issingle": True}})
        references = self.inspect(store, dynamic=[Record(parent="Business Settings", fieldname="reference_name", options="reference_type")])
        self.assertEqual(references, [{"doctype": "Business Settings", "name": "Business Settings"}])


class TestLegacyCleanup(unittest.TestCase):
    def environment(self, store, archive):
        stack = ExitStack()
        stack.enter_context(patch.object(legacy_cleanup, "frappe", store.frappe))
        stack.enter_context(patch.object(legacy_cleanup, "_read_archive", return_value=archive))
        return stack

    def test_converted_proposals_and_repurposed_packages_are_preserved(self):
        store = FakeDatabase({
            "Solar Proposal": [record("Solar Proposal", "CONVERTED", calculation_version="Templates v1")],
            "Solar Package": [record("Solar Package", "REPURPOSED", component_rules=[{"template_alias": "new"}]),
                              record("Solar Package", "INPUTS", input_definitions=[{"variable_key": "distance"}]),
                              record("Solar Package", "DEMO", is_demo=1)]})
        original = {"proposals": [{"name": "CONVERTED"}], "packages": [{"name": name} for name in ["REPURPOSED", "INPUTS", "DEMO"]]}
        with self.environment(store, original), patch.object(legacy_cleanup, "dependencies", return_value=[]), \
                patch.object(legacy_cleanup, "_archive_documents") as archive:
            report = legacy_cleanup.cleanup_unused_legacy_configuration()
        self.assertEqual(report["deleted"], [])
        self.assertEqual({row["name"] for row in report["retained"]}, {"CONVERTED", "REPURPOSED", "INPUTS", "DEMO"})
        store.frappe.delete_doc.assert_not_called()
        archive.assert_not_called()

    def test_full_documents_are_archived_before_proposals_then_packages_are_deleted(self):
        store = FakeDatabase({"Solar Proposal": [record("Solar Proposal", "OLD-PROP", calculation_version="Legacy",
                                  cost_breakdown=[{"description": "Preserve full charge row", "amount": 750}])],
                              "Solar Package": [record("Solar Package", "OLD-PACKAGE", component_rules=[], input_definitions=[])]})
        original = {"proposals": [{"name": "OLD-PROP"}], "packages": [{"name": "OLD-PACKAGE"}]}
        events = []

        def archive(documents):
            events.append("archive")
            return "/private/backups/legacy-cleanup.json"

        def delete(doctype, name, **kwargs):
            events.append((doctype, name))
            self.assertTrue(events.index("archive") < len(events) - 1)
            self.assertEqual(kwargs.get("ignore_permissions"), True)
            self.assertNotIn("force", kwargs)
            self.assertNotIn("delete_permanently", kwargs)
            store.delete(doctype, name)

        store.frappe.delete_doc.side_effect = delete
        with self.environment(store, original), patch.object(legacy_cleanup, "dependencies", return_value=[]), \
                patch.object(legacy_cleanup, "_archive_documents", side_effect=archive) as writer:
            report = legacy_cleanup.cleanup_unused_legacy_configuration()
        self.assertEqual(report["deleted"], [{"doctype": "Solar Proposal", "name": "OLD-PROP"},
                                             {"doctype": "Solar Package", "name": "OLD-PACKAGE"}])
        self.assertEqual([event for event in events if isinstance(event, tuple)],
                         [("Solar Proposal", "OLD-PROP"), ("Solar Package", "OLD-PACKAGE")])
        archived = [doc for call in writer.call_args_list for doc in call.args[0]]
        proposal = next(doc for doc in archived if doc.get("doctype") == "Solar Proposal")
        self.assertEqual(proposal["cost_breakdown"][0]["amount"], 750)
        self.assertEqual(report["archive"], "/private/backups/legacy-cleanup.json")

    def test_link_race_rolls_back_delete_side_effects_and_preserves_record(self):
        store = FakeDatabase({"Solar Proposal": [record("Solar Proposal", "RACED", calculation_version="Legacy")]})
        store.frappe.delete_doc.side_effect = store.frappe.LinkExistsError("A new Project now references the proposal")
        original = {"proposals": [{"name": "RACED"}], "packages": []}
        with self.environment(store, original), patch.object(legacy_cleanup, "dependencies", return_value=[]), \
                patch.object(legacy_cleanup, "_archive_documents", return_value="/private/backups/cleanup.json"):
            report = legacy_cleanup.cleanup_unused_legacy_configuration()
        self.assertEqual(report["deleted"], [])
        self.assertEqual(report["retained"][0]["name"], "RACED")
        store.frappe.db.savepoint.assert_called()
        store.frappe.db.rollback.assert_called_once()

    def test_rerun_does_not_redelete_missing_records_or_archive_them(self):
        store = FakeDatabase()
        original = {"proposals": [{"name": "GONE"}], "packages": [{"name": "GONE-PACKAGE"}]}
        with self.environment(store, original), patch.object(legacy_cleanup, "_archive_documents") as archive:
            first = legacy_cleanup.cleanup_unused_legacy_configuration()
            second = legacy_cleanup.cleanup_unused_legacy_configuration()
        self.assertEqual(first, second)
        self.assertEqual(first["deleted"], [])
        self.assertIsNone(first["archive"])
        store.frappe.delete_doc.assert_not_called()
        archive.assert_not_called()

    def test_missing_original_archive_refuses_deletion(self):
        store = FakeDatabase()
        with self.environment(store, None):
            with self.assertRaises(ValueError):
                legacy_cleanup.cleanup_unused_legacy_configuration()
        store.frappe.delete_doc.assert_not_called()

    def test_complete_archive_is_private_and_contains_every_child_table(self):
        fake = MagicMock()
        fake.local.site = "test.local"
        document = record("Solar Proposal", "OLD", cost_breakdown=[{"description": "Labour", "amount": 250}],
                          total_bom=[{"item_code": "CABLE", "quantity": 12, "rate": 66}])
        with tempfile.TemporaryDirectory() as directory:
            fake.get_site_path.return_value = directory
            with patch.object(legacy_cleanup, "frappe", fake):
                filename = legacy_cleanup._archive_documents([document])
            archive = Path(filename)
            data = json.loads(archive.read_text())
            self.assertEqual(stat.S_IMODE(archive.stat().st_mode), 0o600)
            self.assertEqual(data["site"], "test.local")
            self.assertEqual(data["documents"][0]["cost_breakdown"][0]["amount"], 250)
            self.assertEqual(data["documents"][0]["total_bom"][0]["quantity"], 12)

    def test_archive_failure_prevents_any_deletion(self):
        store = FakeDatabase({"Solar Proposal": [record("Solar Proposal", "OLD", calculation_version="Legacy")]})
        original = {"proposals": [{"name": "OLD"}], "packages": []}
        with self.environment(store, original), patch.object(legacy_cleanup, "_archive_documents", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                legacy_cleanup.cleanup_unused_legacy_configuration()
        store.frappe.delete_doc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
