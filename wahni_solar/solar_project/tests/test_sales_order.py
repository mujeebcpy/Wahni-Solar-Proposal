"""Project material valuation is distinct from customer selling prices."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from wahni_solar.solar_project import sales_order
from wahni_solar.solar_project.tests.helpers import Record


class TestProjectSalesOrder(unittest.TestCase):
    def project(self, **values):
        fields = dict(name="PROJECT", customer="CUSTOMER", custom_solar_proposal="PROPOSAL",
                      custom_table_project_bom=[Record(item_code="CABLE", quantity=8, uom="Meter", rate=100)])
        fields.update(values)
        return Record(fields)

    def test_project_loader_checks_permission_and_exposes_the_shared_pricing_mode(self):
        project = self.project()
        with patch.object(sales_order, "frappe") as fake:
            fake.get_doc.return_value = project
            fake.db.get_value.return_value = "Templates v1"
            result = sales_order.get_project_materials("PROJECT")
        self.assertTrue(result["use_selling_prices"])
        self.assertEqual(result["items"], [{"item_code": "CABLE", "quantity": 8, "uom": "Meter", "rate": 100}])
        project.denied = True
        with patch.object(sales_order.frappe, "get_doc", return_value=project), self.assertRaises(frappe.PermissionError):
            sales_order.get_project_materials("PROJECT")

    def test_source_template_marks_copied_materials_as_costs_without_a_proposal_link(self):
        project = self.project(custom_solar_proposal=None,
                               custom_table_project_bom=[Record(item_code="CABLE", source_template="Downrun")])
        self.assertTrue(sales_order._uses_valuation_rates(project))

    def mapped_order(self, version, source_template=None):
        project = self.project()
        project.custom_table_project_bom[0].source_template = source_template
        target = Record(rate=None)
        order = Record(customer="CUSTOMER", items=[target], run_method=MagicMock())
        mapping = {}

        def mapper(doctype, name, table_maps, target_doc, postprocess):
            mapping.update(table_maps["Solar Proposal BOM Item"])
            mapping["postprocess"](project.custom_table_project_bom[0], target, project)
            postprocess(project, order)
            return order

        with patch.object(sales_order, "frappe") as fake, \
                patch.object(sales_order, "get_mapped_doc", side_effect=mapper):
            fake.db.get_value.return_value = version
            result = sales_order.make_sales_order("PROJECT")
        return result, target, mapping

    def test_new_valuation_rates_are_not_mapped_into_sales_rates(self):
        result, target, mapping = self.mapped_order("Templates v1")
        self.assertIn("rate", mapping["field_no_map"])
        self.assertIn("amount", mapping["field_no_map"])
        self.assertEqual(mapping["field_map"], {"quantity": "qty"})
        self.assertIsNone(target.rate)
        self.assertIsNone(target.price_list_rate)
        self.assertEqual([call.args[0] for call in result.run_method.call_args_list],
                         ["set_missing_values", "calculate_taxes_and_totals"])

    def test_legacy_sales_orders_retain_the_saved_material_rate(self):
        _, target, _ = self.mapped_order("Legacy")
        self.assertEqual(target.rate, 100)

    def test_valuation_rows_remain_safe_when_the_linked_proposal_is_legacy(self):
        _, target, _ = self.mapped_order("Legacy", source_template="Downrun")
        self.assertIsNone(target.rate)
