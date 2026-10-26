"""Remove unused legacy proposals/packages after archiving and dependency checks."""


def execute():
    import frappe
    from wahni_solar.wahni_solar_proposal.legacy_cleanup import cleanup_unused_legacy_configuration

    report = cleanup_unused_legacy_configuration()
    frappe.logger("solar_legacy_cleanup").info(frappe.as_json(report))
    print(f"Solar legacy cleanup: {len(report['deleted'])} removed; {len(report['retained'])} retained.")
