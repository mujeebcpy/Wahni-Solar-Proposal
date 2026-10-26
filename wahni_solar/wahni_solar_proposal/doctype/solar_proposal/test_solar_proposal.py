# Copyright (c) 2026, mujeebcpy and Contributors
# See license.txt

import copy
import unittest
from unittest.mock import MagicMock, patch

import frappe

from wahni_solar.wahni_solar_proposal import api, configuration
from wahni_solar.wahni_solar_proposal.doctype.solar_proposal import solar_proposal


class ProposalRecord(frappe._dict):
    def is_new(self):
        return bool(self.get("new_record"))

    def get_doc_before_save(self):
        return self.get("previous")

    def set_customer_name(self):
        self.customer_name = "Saved customer"

    def set(self, key, value):
        self[key] = value


def fail(message, *args, **kwargs):
    raise ValueError(message)


class TestSolarProposal(unittest.TestCase):
    def record(self, **values):
        record = ProposalRecord(
            doctype="Solar Proposal", name="PROPOSAL", proposal_to="Customer", party="CUSTOMER",
            is_demo=0, flags=frappe._dict(), new_record=False, calculation_version="Legacy",
            previous=None, material_cost=100, other_cost=20, project_cost=120, final_amount=110,
            table_proposal_bom=[{"item_code": "OLD-ITEM", "quantity": 2, "rate": 50}],
        )
        record.update(values)
        return record

    def result(self, **values):
        return dict(calculation_version=configuration.VERSION, costing_status="Complete",
                    material_cost=200, other_cost=20, project_cost=220, final_amount=210, **values)

    def test_new_proposal_cannot_request_legacy_mode_to_skip_calculation(self):
        document = self.record(new_record=True, calculation_version="Legacy")
        with patch.object(configuration, "calculate", return_value=self.result()) as calculate:
            solar_proposal.SolarProposal.validate(document)
        calculate.assert_called_once()
        self.assertEqual(document.calculation_version, configuration.VERSION)
        self.assertEqual(document.material_cost, 200)

    def test_existing_template_proposal_cannot_downgrade_to_legacy(self):
        previous = self.record(calculation_version=configuration.VERSION)
        document = self.record(previous=previous, calculation_version="Legacy")
        with patch.object(configuration, "calculate", return_value=self.result()) as calculate:
            solar_proposal.SolarProposal.validate(document)
        self.assertIs(calculate.call_args.kwargs["previous"], previous)
        self.assertEqual(document.calculation_version, configuration.VERSION)
        self.assertEqual(document.project_cost, 220)

    def test_genuine_legacy_save_retains_its_cost_history_until_explicit_regeneration(self):
        previous = self.record(calculation_version=None)
        document = self.record(previous=previous, calculation_version=configuration.VERSION)
        before = {key: copy.deepcopy(document[key]) for key in (
            "material_cost", "other_cost", "project_cost", "final_amount", "table_proposal_bom"
        )}
        with patch.object(configuration, "calculate") as calculate:
            solar_proposal.SolarProposal.validate(document)
        calculate.assert_not_called()
        self.assertEqual(document.calculation_version, "Legacy")
        self.assertEqual({key: document[key] for key in before}, before)

    def test_explicit_regeneration_upgrades_a_legacy_document(self):
        document = self.record(previous=self.record())
        document.flags.regenerate_configuration = True
        with patch.object(configuration, "calculate", return_value=self.result()) as calculate:
            solar_proposal.SolarProposal.validate(document)
        self.assertTrue(calculate.call_args.kwargs["regenerate"])
        self.assertEqual(document.calculation_version, configuration.VERSION)

    def test_print_checks_persisted_version_and_rejects_unresolved_valuation(self):
        previous = self.record(calculation_version=configuration.VERSION)
        document = self.record(calculation_version="Legacy")
        result = self.result()
        result["costing_status"] = "Missing Valuation / Conversion"
        with patch.object(solar_proposal.frappe, "get_doc", return_value=previous), \
                patch.object(configuration, "calculate", return_value=result) as calculate, \
                patch.object(solar_proposal.frappe, "throw", side_effect=fail):
            with self.assertRaisesRegex(ValueError, "Resolve missing valuations"):
                solar_proposal.SolarProposal.before_print(document)
        calculate.assert_called_once()
        self.assertEqual(document.calculation_version, configuration.VERSION)

    def test_genuine_legacy_print_does_not_reload_pricing(self):
        previous = self.record(calculation_version="Legacy")
        document = self.record()
        with patch.object(solar_proposal.frappe, "get_doc", return_value=previous), \
                patch.object(configuration, "calculate") as calculate:
            solar_proposal.SolarProposal.before_print(document)
        calculate.assert_not_called()
        self.assertEqual(document.project_cost, 120)


class TestSolarProposalPreviewAPI(unittest.TestCase):
    def test_required_input_controls_bootstrap_before_their_values_can_be_calculated(self):
        snapshot = {"input_definitions": [{
            "variable_key": "route_length", "label": "Route Length", "input_type": "Float",
            "default_value": "", "required": 1,
        }]}
        with patch.object(configuration, "load_configuration", return_value=snapshot), \
                patch.object(configuration, "system_context") as calculate:
            rows = api.package_inputs("PACKAGE")
        calculate.assert_not_called()
        self.assertEqual(rows[0]["variable_key"], "route_length")
        self.assertEqual(rows[0]["value"], "")
        self.assertEqual(rows[0]["required"], 1)

    def test_bootstrap_preserves_site_values_and_defaults_only_new_keys(self):
        snapshot = {"input_definitions": [
            {"variable_key": "existing", "input_type": "Float", "default_value": "25"},
            {"variable_key": "new_input", "input_type": "Float", "default_value": "8"},
        ]}
        with patch.object(configuration, "load_configuration", return_value=snapshot):
            rows = api.package_inputs("PACKAGE", supplied=[{"variable_key": "existing", "value": "0"}])
        self.assertEqual([row["value"] for row in rows], ["0", "8"])

    def test_preview_checks_write_permission_on_persisted_document(self):
        incoming = MagicMock(name="incoming")
        incoming.name = "EXISTING"
        previous = MagicMock()
        with patch.object(api, "frappe") as fake:
            fake.get_doc.side_effect = [incoming, previous]
            fake.db.exists.return_value = True
            document, saved = api.proposal_document({"doctype": "Solar Proposal", "name": "EXISTING"})
        self.assertIs(document, incoming)
        self.assertIs(saved, previous)
        previous.check_permission.assert_called_once_with("write")
        incoming.check_permission.assert_not_called()

    def test_preview_checks_create_permission_for_new_document(self):
        incoming = MagicMock()
        incoming.name = None
        with patch.object(api, "frappe") as fake:
            fake.get_doc.return_value = incoming
            document, saved = api.proposal_document({"doctype": "Solar Proposal"})
        self.assertIs(document, incoming)
        self.assertIsNone(saved)
        incoming.check_permission.assert_called_once_with("create")
