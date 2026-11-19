import { describe, expect, it } from "vitest"
import { completionRequired, evaluateCondition, isVisible, missingForCompletion } from "@/utils/conditions"
import { fromGeoJSON, isSecureOrigin, locationPermissionState, mapsUrl, safeHttpUrl, toGeoJSON, validCoordinates } from "@/utils/geo"

describe("evaluateCondition (safe subset, no JS eval)", () => {
	const doc = { loan_requirement: "Yes", name_correction: "No", customer: "", status: "In Progress", count: 0 }
	it.each([
		["eval:doc.loan_requirement == 'Yes'", true],
		["eval:doc.loan_requirement === \"Yes\"", true],
		["eval:doc.name_correction == 'Yes'", false],
		["eval:doc.name_correction != 'Yes'", true],
		["eval:doc.customer", false],
		["eval:!doc.customer", true],
		["eval:!!doc.loan_requirement", true],
		["eval:doc.__islocal", false],
		["eval:!doc.customer && doc.loan_requirement == 'Yes'", true],
		["eval:doc.customer || doc.name_correction == 'Yes'", false],
		["loan_requirement", true],
		["count", false],
	])("%s -> %s", (expr, value) => {
		expect(evaluateCondition(expr, doc)).toEqual({ supported: true, value })
	})
	it.each([
		"eval:frappe.user.has_role('X')",
		"eval:(doc.a == 'b')",
		"eval:doc.a == 'b' && doc.c || doc.d",
		"eval:doc.items.length > 0",
		"eval:alert(1)",
	])("unsupported %s defaults to visible and is flagged", (expr) => {
		expect(evaluateCondition(expr, doc)).toEqual({ supported: false, value: true })
	})
})

describe("completion requirements", () => {
	const fields = [
		{ fieldname: "visit_date", fieldtype: "Date", mandatory_depends_on: "eval:doc.status == 'Completed'" },
		{ fieldname: "customer_name", fieldtype: "Data", reqd: 1 },
		{ fieldname: "notes", fieldtype: "Text" },
		{ fieldname: "weird", fieldtype: "Data", mandatory_depends_on: "eval:frappe.boot.x" },
		{ fieldname: "table", fieldtype: "Table", reqd: 1, supported: false },
	]
	it("evaluates mandatory_depends_on as if completing", () => {
		expect(completionRequired(fields[0], { status: "In Progress" })).toBe(true)
		expect(completionRequired(fields[3], {})).toBe(false) // server stays authoritative
		const missing = missingForCompletion(fields, { status: "In Progress", customer_name: "  " })
		expect(missing.map((f) => f.fieldname)).toEqual(["visit_date", "customer_name"])
		expect(missingForCompletion(fields, { visit_date: "2026-11-17", customer_name: "A" })).toEqual([])
	})
	it("hides conditional fields", () => {
		expect(isVisible({ depends_on: "eval:doc.loan_requirement == 'Yes'" }, { loan_requirement: "No" })).toBe(false)
		expect(isVisible({}, {})).toBe(true)
	})
})

describe("geolocation", () => {
	it("round-trips the Frappe GeoJSON format", () => {
		const value = toGeoJSON(10.5276, 76.2144)
		expect(JSON.parse(value).features[0].geometry).toEqual({ type: "Point", coordinates: [76.2144, 10.5276] })
		expect(fromGeoJSON(value)).toEqual({ lat: 10.5276, lng: 76.2144 })
		expect(fromGeoJSON("not json")).toBeNull()
		expect(fromGeoJSON('{"type":"FeatureCollection","features":[]}')).toBeNull()
	})
	it("validates coordinates and links", () => {
		expect(validCoordinates("10.5", "76.2")).toBe(true)
		expect(validCoordinates("91", "0")).toBe(false)
		expect(validCoordinates("", "1")).toBe(false)
		expect(mapsUrl({ lat: 1, lng: 2 })).toContain("query=1,2")
		expect(safeHttpUrl("javascript:alert(1)")).toBeNull()
		expect(safeHttpUrl("https://maps.app/x")).toBe("https://maps.app/x")
	})
})

describe("location prerequisites", () => {
	it("needs a secure context (https or localhost)", () => {
		expect(isSecureOrigin({ isSecureContext: true })).toBe(true)
		expect(isSecureOrigin({ isSecureContext: false })).toBe(false)
		expect(isSecureOrigin(undefined)).toBe(false)
	})
	it("reads the permission state when the Permissions API exists", async () => {
		const nav = { permissions: { query: async () => ({ state: "denied" }) } }
		expect(await locationPermissionState(nav)).toBe("denied")
		expect(await locationPermissionState({})).toBe(null)
		expect(await locationPermissionState({ permissions: { query: async () => { throw new Error("x") } } })).toBe(null)
	})
})
