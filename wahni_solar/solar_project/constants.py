"""The report order is stable, regardless of attachment names or upload order."""

PANEL_DOCUMENT = "Panel Datasheet and BIS"
# Retained for existing records and snapshots; new reports use the combined PDF.
LEGACY_PANEL_CATEGORIES = ("Panel Datasheet", "Panel BIS")

SECTIONS = (
    "Cover Page",
    "Application Acknowledgement Report",
    "Annexure I",
    "Feasibility Report",
    "PM-Surya Ghar E-Token",
    "Annexure II",
    "Annexure III",
    "Single Line Diagram",
    "Check List",
    "Project Completion Report",
    PANEL_DOCUMENT,
    "Panel DCR Certificate",
    "Panel Warranty Certificate",
    "Inverter Datasheet",
    "Inverter BIS",
    "Inverter Warranty Card",
    "Meter Calibration Test Report",
    "ACDB SPD Datasheet",
    "ACDB MCB Datasheet",
    "Earth Kit Datasheets",
    "Plant Commissioning Certificate",
    "Sales Invoice",
    "Customer Vendor Agreement",
    "End Page",
)
LIBRARY_CATEGORIES = (*SECTIONS, "SLD Template")
OPTIONAL_SECTIONS = {"Cover Page", "End Page", "Sales Invoice"}
FORM_SECTIONS = {"Check List", "Project Completion Report"}
ANNEXURES = {"Annexure I": 1, "Annexure II": 2, "Annexure III": 3}
ACTIVE_STATUSES = ("Queued", "Running")
