"""Archive the retired BOM-based configuration before removing its columns."""

import json
import os
import tempfile
from pathlib import Path

import frappe
from frappe.database.schema import add_column
from frappe.utils import now_datetime

ARCHIVE_NAME = "wahni-solar-legacy-configuration-v1.json"
RETIRED_PACKAGE_FIELDS = (
    "inverter_bom_item", "basic_bom_item", "connection_type",
    "panel_capacity_min", "panel_capacity_max", "description",
)


def archive_path():
    return Path(frappe.get_site_path("private", "backups", ARCHIVE_NAME))


def _read_archive():
    path = archive_path()
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if data.get("archive_version") != 1 or data.get("site") != frappe.local.site:
        raise ValueError(f"Unexpected solar configuration archive at {path}; no retired data was removed.")
    os.chmod(path, 0o600)
    return data


def _write_archive(data):
    """Publish a complete private archive atomically, without replacing an earlier one."""
    path = archive_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".solar-configuration-", dir=path.parent)
    try:
        with os.fdopen(handle, "w") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        # link() is atomic and fails if a prior migration already published its archive.
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
    finally:
        os.unlink(temporary)
    return _read_archive()


def _all_rows(doctype):
    if not frappe.db.table_exists(doctype):
        return []
    return frappe.get_all(doctype, fields=["*"], limit_page_length=0)


def prepare_legacy_configuration():
    """Pre-model-sync: archive old values and populate the new unique package title."""
    data = _read_archive()
    if data is None:
        packages = _all_rows("Solar Package")
        legacy_packages = [dict(row) for row in packages if any(row.get(field) for field in RETIRED_PACKAGE_FIELDS)]
        proposals = [dict(row) for row in _all_rows("Solar Proposal")
                     if row.get("calculation_version") != "Templates v1"]
        materials = [dict(row) for row in _all_rows("Solar Proposal BOM Item")
                     if not row.get("source_template")]
        codes = sorted({row["item_code"] for row in materials if row.get("item_code")})
        item_rows = frappe.get_all("Item", filters={"name": ["in", codes]},
                                   fields=["name", "item_name", "item_group", "description", "stock_uom"],
                                   limit_page_length=0) if codes else []
        setters = frappe.get_all("Property Setter", filters={
            "doc_type": "Solar Package", "field_name": ["in", RETIRED_PACKAGE_FIELDS]},
            fields=["*"], limit_page_length=0)
        data = _write_archive({
            "archive_version": 1, "site": frappe.local.site, "created_on": str(now_datetime()),
            "retired_package_fields": list(RETIRED_PACKAGE_FIELDS), "packages": legacy_packages,
            "proposals": proposals, "material_rows": materials,
            "item_metadata": {row["name"]: dict(row) for row in item_rows},
            "property_setters": [dict(row) for row in setters],
        })

    if frappe.db.table_exists("Solar Package"):
        if not frappe.db.has_column("Solar Package", "package_title"):
            add_column("Solar Package", "package_title", "Data")
        for row in _all_rows("Solar Package"):
            if not row.get("package_title"):
                frappe.db.set_value("Solar Package", row["name"], "package_title", row["name"], update_modified=False)
    return str(archive_path())


def _legacy_proposal_values(proposal, package):
    values = {"calculation_version": "Legacy", "costing_status": "Legacy"}
    for target, value in {
        "system_name": proposal.get("system_name") or package.get("package_title") or package.get("name") or proposal.get("package_name"),
        "brand": proposal.get("brand") or package.get("brand"),
        "system_type": proposal.get("system_type") or package.get("system_type"),
        "grid_type": proposal.get("grid_type") or package.get("grid_type"),
        "connection_type": proposal.get("connection_type") or package.get("connection_type"),
    }.items():
        if value:
            values[target] = value
    count = proposal.get("inverter_count")
    brand = (values.get("brand") or "").lower()
    if count is None and brand in ("enphase", "vsole"):
        panels = int(proposal.get("panel_count") or 0)
        count = panels if brand == "enphase" else (panels + 1) // 2
    if count is not None:
        values["inverter_count"] = count
    values["configuration_snapshot"] = json.dumps({
        "version": "Legacy", "legacy_package": package, "archive": ARCHIVE_NAME,
    }, default=str)
    return values


def finish_legacy_configuration():
    """Post-model-sync: preserve history, remove unused packages and retired columns."""
    data = _read_archive()
    if data is None:
        # A direct post-sync invocation must never drop values that were not archived.
        if frappe.db.table_exists("Solar Package") and any(
            frappe.db.has_column("Solar Package", field) for field in RETIRED_PACKAGE_FIELDS
        ):
            raise ValueError("The solar legacy configuration archive is missing. Run the pre-sync patch first.")
        return {"deleted_packages": [], "retained_packages": []}

    packages = {row["name"]: row for row in data["packages"]}
    for proposal in data["proposals"]:
        if not frappe.db.exists("Solar Proposal", proposal["name"]):
            continue
        version = frappe.db.get_value("Solar Proposal", proposal["name"], "calculation_version")
        if version == "Templates v1":
            continue
        values = _legacy_proposal_values(proposal, packages.get(proposal.get("package_name"), {}))
        frappe.db.set_value("Solar Proposal", proposal["name"], values, update_modified=False)

    for row in data["material_rows"]:
        if not frappe.db.exists("Solar Proposal BOM Item", row["name"]):
            continue
        if frappe.db.get_value("Solar Proposal BOM Item", row["name"], "source_template"):
            continue
        item = data["item_metadata"].get(row.get("item_code"), {})
        values = {
            "component_group": row.get("component_group") or item.get("item_group") or "Materials",
            "component_label": row.get("component_label") or item.get("item_name") or row.get("item_code"),
            "item_name": row.get("item_name") or item.get("item_name") or row.get("item_code"),
            "description": row.get("description") or item.get("description") or "",
            "stock_uom": row.get("stock_uom") or item.get("stock_uom"),
            "generated_quantity": row.get("quantity") or 0,
            "valuation_status": "Legacy",
        }
        frappe.db.set_value("Solar Proposal BOM Item", row["name"], values, update_modified=False)

    report = {"deleted_packages": [], "retained_packages": []}
    for name in packages:
        if not frappe.db.exists("Solar Package", name):
            continue
        # Legacy packages cannot accidentally generate a new empty template proposal.
        frappe.db.set_value("Solar Package", name, "disabled", 1, update_modified=False)
        if frappe.db.exists("File", {"attached_to_doctype": "Solar Package", "attached_to_name": name}):
            report["retained_packages"].append(name)
            continue
        try:
            frappe.delete_doc("Solar Package", name, ignore_permissions=True)
        except frappe.LinkExistsError:
            report["retained_packages"].append(name)
        else:
            report["deleted_packages"].append(name)

    for setter in data["property_setters"]:
        if frappe.db.exists("Property Setter", setter["name"]):
            frappe.delete_doc("Property Setter", setter["name"], ignore_permissions=True)
    columns = [field for field in RETIRED_PACKAGE_FIELDS if frappe.db.has_column("Solar Package", field)]
    if columns:
        for field in columns:
            if frappe.get_meta("Solar Package").get_field(field):
                raise ValueError(f"Solar Package.{field} is still an active field; refusing to drop its data column.")
        quote = "`" if frappe.db.db_type == "mariadb" else '"'
        drops = ", ".join(f"DROP COLUMN {quote}{field}{quote}" for field in columns)
        frappe.db.sql_ddl(f"ALTER TABLE {quote}tabSolar Package{quote} {drops}")
        frappe.client_cache.delete_value("table_columns::tabSolar Package")
    frappe.clear_cache(doctype="Solar Package")
    return report
