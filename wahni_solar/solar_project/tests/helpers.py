"""Shared test records and paths. No database or site is initialized."""

from pathlib import Path

import frappe

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


class Record(frappe._dict):
    """Minimal document double for source and generation unit tests."""

    def check_permission(self, permission):
        if self.get("denied"):
            raise frappe.PermissionError

    def db_set(self, key, value=None, **kwargs):
        self.update(key if isinstance(key, dict) else {key: value})
