"""Optional, removable configurator examples using the site's existing Items.

These records demonstrate rules; they do not establish an electrical design or
create inventory, valuation rates, customers, companies or transactions.
"""

import re

import frappe
from frappe.utils import cint

SETTINGS = "Wahni Default Settings"
PREFIX = "DEMO — "
METER_UOMS = {"meter", "metre", "meters", "metres", "mtr", "m"}


def _text(item):
    return " ".join(str(item.get(key) or "") for key in ("item_name", "item_group", "name")).lower()


def _pick(items, pattern, *, meters=False, exclude="", prefer=""):
    candidates = [
        item for item in items
        if re.search(pattern, _text(item))
        and (not meters or (item.get("stock_uom") or "").lower() in METER_UOMS)
        and (not exclude or not re.search(exclude, _text(item)))
    ]
    # A broad Item Group such as "Earthing Kit" must not outrank an Item whose
    # actual name identifies the requested role (for example an earthing rod).
    candidates.sort(key=lambda item: (
        not bool(re.search(pattern, " ".join(str(item.get(key) or "") for key in ("item_name", "name")).lower())),
        not bool(prefer and re.search(prefer, _text(item))), item["name"],
    ))
    return candidates[0] if candidates else None


def _discover_items(items):
    """Match material roles, never a fixed site-specific Item code."""
    ac_six_sq = r"(?=.*\bac\b)(?=.*(?:6\s*(?:sq|mm)|6sq))"
    return {
        "inverter": _pick(items, r"micro[ -]?inverter|\biq8", prefer=r"enphase|\biq8"),
        "hybrid_inverter": _pick(items, r"(?=.*hybrid)(?=.*inverter)", exclude=r"cable|connector|battery box"),
        "cable": _pick(items, r"cable|wire", meters=True, exclude=r"communication|ethernet|\blan\b", prefer=ac_six_sq),
        "armoured_cable": _pick(items, r"(?=.*(?:cable|wire))(?=.*(?:armou?red|underground|\bug cable\b))", meters=True),
        "red_cable": _pick(items, r"(?=.*\bred\b)(?=.*(?:cable|wire))", meters=True, prefer=ac_six_sq),
        "black_cable": _pick(items, r"(?=.*\bblack\b)(?=.*(?:cable|wire))", meters=True, prefer=ac_six_sq),
        "yellow_cable": _pick(items, r"(?=.*\byellow\b)(?=.*(?:cable|wire))", meters=True, prefer=ac_six_sq),
        "blue_cable": _pick(items, r"(?=.*\bblue\b)(?=.*(?:cable|wire))", meters=True, prefer=ac_six_sq),
        "clamp": _pick(items, r"clamp|\bclip\b", exclude=r"meter|ammeter", prefer=r"cable|conduit"),
        "screw": _pick(items, r"screw", exclude=r"driver|machine|washer"),
        "wall_plug": _pick(items, r"wall[ -]?plug|rawl[ -]?plug|fischer"),
        "earth": _pick(items, r"earth(ing)? (kit|rod|electrode)|earthing kit"),
        "battery": _pick(items, r"\bbattery\b", exclude=r"inverter|cable|connector|\bbox\b|breaker|fuse|\bmcb\b|\brc[bc]b\b"),
    }


def _row(key, label, item, formula, condition=""):
    return {
        "rule_key": key, "component_label": label, "item_code": item["name"],
        "uom": item["stock_uom"], "quantity_formula": formula, "include_when": condition,
        "description": item.get("description") or item.get("item_name") or item["name"],
        "enabled": 1,
    }


def _insert_demo(doctype, title_field, title, values, report):
    name = frappe.db.get_value(doctype, {title_field: title}, "name")
    if name:
        if not cint(frappe.db.get_value(doctype, name, "is_demo")):
            report["warnings"].append(f"{doctype} {name} already exists without the demo flag; it was left unchanged.")
            return None
        report["existing"].append({"doctype": doctype, "name": name})
        return name
    doc = frappe.get_doc({"doctype": doctype, title_field: title, "is_demo": 1, **values})
    doc.insert(ignore_permissions=True)
    report["created"].append({"doctype": doctype, "name": doc.name})
    return doc.name


@frappe.whitelist()
def seed_demo_configuration():
    """Idempotent setup; staff edits are preserved and cleared defaults stay cleared."""
    frappe.only_for("System Manager")
    report = {"created": [], "existing": [], "warnings": [], "packages": [], "templates": []}
    if cint(frappe.db.get_single_value(SETTINGS, "demo_defaults_cleared")):
        report["warnings"].append("Demo defaults were cleared. Enable demo defaults in Settings before installing them again.")
        return report

    items = frappe.get_all(
        "Item", filters={"disabled": 0, "has_variants": 0, "is_stock_item": 1},
        fields=["name", "item_name", "item_group", "stock_uom", "brand", "description"],
        order_by="name", limit_page_length=0,
    )
    roles = _discover_items(items)
    if not roles["inverter"] or not roles["cable"]:
        report["warnings"].append(
            "Demo setup needs an enabled stock microinverter and a cable whose stock UOM is Meter. "
            "No inventory or placeholder Items were created."
        )
        return report

    cable = roles["cable"]
    templates = {}

    def template(alias, title, group, rows, **extra):
        name = _insert_demo("Solar Component Template", "template_name", PREFIX + title, {
            "group_name": group, "items": rows,
            "notes": "Editable demonstration only. Review Item specifications and rules before using for a customer.",
            **extra,
        }, report)
        if name:
            templates[alias] = name
            report["templates"].append(name)

    downrun_rows = [_row("cable", "Downrun cable", cable, "downrun_length")]
    if roles["armoured_cable"] and roles["armoured_cable"]["name"] != cable["name"]:
        downrun_rows[0]["include_when"] = 'cabling_type == "Conduit Cabling"'
        downrun_rows.append(_row("armoured_cable", "Armoured downrun cable", roles["armoured_cable"],
                                 "downrun_length", 'cabling_type == "Armoured Cabling"'))
    if roles["clamp"]:
        downrun_rows.append(_row("clamp", "Cable supports", roles["clamp"], "ceil(downrun_length * 2)"))
    if roles["screw"]:
        formula = 'qty("clamp") * 2' if roles["clamp"] else "ceil(downrun_length * 4)"
        downrun_rows.append(_row("screw", "Support screws", roles["screw"], formula))
    if roles["wall_plug"] and roles["screw"]:
        downrun_rows.append(_row("wall_plug", "Wall plugs", roles["wall_plug"],
                                 '0 if self_screws else qty("screw")'))
    template("downrun", "Downrun", "Downrun", downrun_rows)

    template("inverter_links", "Micro Inverter to Downrun", "Micro Inverter to Downrun", [
        _row("inverter", "Micro inverter", roles["inverter"], "inverter_count"),
    ])
    looping = []
    for colour in ("red", "black", "yellow", "blue"):
        if item := roles[f"{colour}_cable"]:
            looping.append(_row(f"{colour}_cable", f"{colour.title()} DB looping cable", item,
                                "db_loop_length", 'phase == "Three Phase"' if colour in ("yellow", "blue") else ""))
    if not looping:
        looping.append(_row("loop_cable", "DB looping cable", cable,
                            'db_loop_length * (4 if phase == "Three Phase" else 2)'))
    template("db_loop", "Downrun to DB Looping", "Downrun to DB Looping", looping)

    common = [_row("earth_kit", "Earthing", roles["earth"], "1")] if roles["earth"] else []
    template("common", "Common for all", "Common for all", common)
    if not common:
        report["warnings"].append("No earthing kit Item was identified; the Common for all demo template is empty and editable.")
    if roles["battery"]:
        template("battery", "Battery Materials", "Battery and Battery DB", [
            _row("battery", "Battery", roles["battery"], "battery_count", "include_battery"),
        ])

    required_aliases = ("downrun", "inverter_links", "db_loop", "common")
    if any(alias not in templates for alias in required_aliases):
        report["warnings"].append("The demo package was not created because a required demo template name is occupied by a non-demo record.")
        return report
    definitions = [
        {"variable_key": "downrun_length", "label": "Downrun Length", "input_type": "Float",
         "uom": cable["stock_uom"], "default_value": "25", "required": 1},
        {"variable_key": "db_loop_length", "label": "DB Looping Length", "input_type": "Float",
         "uom": cable["stock_uom"], "default_value": "8", "required": 1},
        {"variable_key": "self_screws", "label": "Use Self Screws", "input_type": "Check", "default_value": "0"},
        {"variable_key": "battery_count", "label": "Number of Batteries", "input_type": "Int",
         "default_value": "1", "show_when": "include_battery", "required": 1},
    ]
    links = [{"template_alias": alias, "component_template": templates[alias], "enabled": 1}
             for alias in required_aliases]
    inverter = roles["inverter"]
    inverter_formula = "ceil(panel_count / 2)" if "vsole" in _text(inverter) else "panel_count"
    package_name = _insert_demo("Solar Package", "package_title", PREFIX + "Micro Inverter System", {
        "brand": inverter.get("brand"), "system_type": "Micro", "grid_type": "On-Grid",
        "inverter_count_formula": inverter_formula, "allow_battery": 0,
        "component_rules": links, "input_definitions": definitions,
    }, report)
    if package_name:
        report["packages"].append(package_name)

    if roles["hybrid_inverter"] and "battery" in templates:
        hybrid = roles["hybrid_inverter"]
        template("hybrid_inverter", "Hybrid Inverter", "Inverters", [
            _row("inverter", "Hybrid inverter", hybrid, "inverter_count"),
        ])
        if "hybrid_inverter" in templates:
            hybrid_links = [dict(row) for row in links]
            hybrid_links[1]["component_template"] = templates["hybrid_inverter"]
            hybrid_links.append({"template_alias": "battery", "component_template": templates["battery"],
                                 "include_when": "include_battery", "enabled": 1})
            name = _insert_demo("Solar Package", "package_title", PREFIX + "Hybrid with Optional Battery", {
                "brand": hybrid.get("brand"), "system_type": "Hybrid", "grid_type": "Hybrid",
                "inverter_count_formula": "1", "allow_battery": 1,
                "component_rules": hybrid_links, "input_definitions": definitions,
            }, report)
            if name:
                report["packages"].append(name)
    return report


@frappe.whitelist()
def clear_demo_configuration():
    """Remove only demo-tagged, unreferenced records; never force link checks."""
    frappe.only_for("System Manager")
    report = {"deleted": [], "skipped": []}
    frappe.db.set_single_value(SETTINGS, "demo_defaults_cleared", 1)
    for doctype in ("Solar Proposal", "Solar Package", "Solar Component Template"):
        names = frappe.get_all(doctype, filters={"is_demo": 1}, pluck="name")
        for name in names:
            if frappe.db.exists("File", {"attached_to_doctype": doctype, "attached_to_name": name}):
                report["skipped"].append({"doctype": doctype, "name": name, "reason": "Has attached files; preserved to avoid deleting staff uploads."})
                continue
            if doctype == "Solar Proposal" and frappe.db.exists("Project", {"custom_solar_proposal": name}):
                report["skipped"].append({"doctype": doctype, "name": name, "reason": "Used by a Project."})
                continue
            try:
                frappe.delete_doc(doctype, name, ignore_permissions=True)
            except frappe.LinkExistsError:
                report["skipped"].append({"doctype": doctype, "name": name, "reason": "Referenced by another record."})
            else:
                report["deleted"].append({"doctype": doctype, "name": name})
    return report
