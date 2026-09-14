"""Repeatable default library and brand setup."""

import unittest
from unittest.mock import MagicMock, patch

from wahni_solar.solar_project import equipment
from wahni_solar.solar_project.tests.helpers import TEMPLATES


class TestReportSetup(unittest.TestCase):
    def test_seed_library_does_not_replace_existing_user_files(self):
        from wahni_solar.solar_project import setup
        fake = MagicMock()
        fake.get_app_path.return_value = str(TEMPLATES)
        fake.db.exists.return_value = True
        with patch.object(setup, "frappe", fake), patch.object(setup, "save_file") as save:
            setup.seed_library()
        save.assert_not_called()

    def test_brand_setup_creates_only_missing_masters(self):
        fake = MagicMock()
        fake.get_all.return_value = ["Enphase", "Vsole"]
        existing = {"Enphase"}
        fake.db.exists.side_effect = lambda doctype, name: name in existing
        def get_doc(values):
            doc = MagicMock()
            doc.insert.side_effect = lambda **kwargs: existing.add(values["brand"])
            return doc
        fake.get_doc.side_effect = get_doc
        with patch.object(equipment, "frappe", fake):
            equipment.migrate_package_brands()
            equipment.migrate_package_brands()
        self.assertEqual(existing, {"Enphase", "Vsole"})
        fake.get_doc.assert_called_once_with({"doctype": "Brand", "brand": "Vsole"})
