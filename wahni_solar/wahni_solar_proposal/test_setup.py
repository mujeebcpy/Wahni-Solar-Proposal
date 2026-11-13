"""Fresh-install costing defaults preserve existing configuration."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from wahni_solar.wahni_solar_proposal import setup


class TestCostingDefaults(unittest.TestCase):
    def test_default_company_without_warehouses_uses_only_existing_stock_company(self):
        fake = MagicMock()
        fake.get_single.return_value = SimpleNamespace(costing_company=None, valuation_warehouse=None)
        fake.defaults.get_global_default.return_value = "No Stock Company"
        fake.db.get_single_value.return_value = None
        fake.get_all.return_value = [{"name": "Stores - WGT", "company": "WGT", "warehouse_name": "Stores"}]
        with patch.object(setup, "frappe", fake):
            self.assertEqual(setup.set_costing_defaults(), [])
        writes = [call.args for call in fake.db.set_single_value.call_args_list]
        self.assertIn((setup.SETTINGS, "costing_company", "WGT"), writes)
        self.assertIn((setup.SETTINGS, "valuation_warehouse", "Stores - WGT"), writes)

    def test_existing_valid_costing_settings_are_preserved(self):
        fake = MagicMock()
        fake.get_single.return_value = SimpleNamespace(costing_company="WGT", valuation_warehouse="Chosen - WGT")
        fake.db.get_single_value.return_value = None
        fake.get_all.return_value = [{"name": "Chosen - WGT", "company": "WGT", "warehouse_name": "Chosen"}]
        with patch.object(setup, "frappe", fake):
            setup.set_costing_defaults()
        fake.db.set_single_value.assert_not_called()


if __name__ == "__main__":
    unittest.main()
