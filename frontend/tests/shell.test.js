import { describe, expect, it } from "vitest"
import { decideNavigation } from "@/router/guard"
import { safeRedirect } from "@/utils/redirect"
import { translate } from "@/plugins/translation"
import { isIOS } from "@/composables/useInstall"
import { routes } from "@/router"

const allowed = { allowed: true }

describe("safeRedirect", () => {
	it("accepts in-app paths", () => {
		expect(safeRedirect("/site-visits/SV-2026-00001")).toBe("/site-visits/SV-2026-00001")
		expect(safeRedirect("/expenses?status=Draft")).toBe("/expenses?status=Draft")
	})
	it.each([
		"//evil.example.com", "/\\evil.example.com", "https://evil.example.com", "javascript:alert(1)",
		"/javascript:alert(1)", "", null, undefined, 42, "/login", "/login?redirect=/x", "/a\\b", "/a\nb",
	])("rejects %s", (value) => {
		expect(safeRedirect(value)).toBeNull()
	})
})

describe("decideNavigation", () => {
	it("sends guests to login, keeping the target", () => {
		expect(decideNavigation({ name: "SiteVisit", fullPath: "/site-visits/SV-1" }, { loggedIn: false }))
			.toEqual({ name: "Login", query: { redirect: "/site-visits/SV-1" } })
		expect(decideNavigation({ name: "Home", fullPath: "/" }, { loggedIn: false })).toEqual({ name: "Login", query: {} })
		expect(decideNavigation({ name: "Login" }, { loggedIn: false })).toBeNull()
		expect(decideNavigation({ name: "ForgotPassword" }, { loggedIn: false })).toBeNull()
	})
	it("blocks users who are not eligible", () => {
		const info = { allowed: false, reason: "No employee" }
		expect(decideNavigation({ name: "Home" }, { loggedIn: true, info })).toEqual({ name: "AccessDenied" })
		expect(decideNavigation({ name: "AccessDenied" }, { loggedIn: true, info })).toBeNull()
		expect(decideNavigation({ name: "Home" }, { loggedIn: true, info: null })).toEqual({ name: "AccessDenied" })
	})
	it("returns logged-in users from login to a safe target", () => {
		expect(decideNavigation({ name: "Login", query: { redirect: "/pms-visits" } }, { loggedIn: true, info: allowed })).toBe("/pms-visits")
		expect(decideNavigation({ name: "Login", query: { redirect: "//evil.com" } }, { loggedIn: true, info: allowed })).toEqual({ name: "Home" })
		expect(decideNavigation({ name: "AccessDenied", query: {} }, { loggedIn: true, info: allowed })).toEqual({ name: "Home" })
		expect(decideNavigation({ name: "Expenses", query: {} }, { loggedIn: true, info: allowed })).toBeNull()
	})
})

describe("routes", () => {
	it("cover every planned /field screen", () => {
		const shell = routes.find((route) => route.path === "/")
		const paths = shell.children.map((route) => route.path)
		// "<section>/new" is served by "<section>/:name" (name === "new").
		for (const path of ["", "site-visits", "site-visits/:name", "pms-visits", "pms-visits/:name", "expenses", "expenses/:name"]) {
			expect(paths).toContain(path)
		}
		expect(routes.map((route) => route.path)).toContain("/login")
	})
})

describe("translate", () => {
	it("uses boot messages and fills placeholders", () => {
		expect(translate("Hello {0}", ["Asha"], { "Hello {0}": "Namaskaram {0}" })).toBe("Namaskaram Asha")
		expect(translate("Untranslated", null, {})).toBe("Untranslated")
	})
})

describe("isIOS", () => {
	it("detects iPhone and iPadOS", () => {
		expect(isIOS("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)", 5)).toBe(true)
		expect(isIOS("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", 5)).toBe(true)
		expect(isIOS("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", 0)).toBe(false)
		expect(isIOS("Mozilla/5.0 (Linux; Android 14; Pixel 8)", 5)).toBe(false)
	})
})
