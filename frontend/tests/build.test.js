// Guards the generated worker (run after `yarn build`).
import fs from "fs"
import path from "path"
import { describe, expect, it } from "vitest"

const out = path.resolve(__dirname, "../../wahni_solar/public/field")
const worker = path.join(out, "sw.js")
const built = fs.existsSync(worker)

describe.skipIf(!built)("generated service worker", () => {
	const source = built ? fs.readFileSync(worker, "utf8") : ""
	const urls = [...source.matchAll(/url:"([^"]+)"/g)].map((m) => m[1])

	it("precaches only absolute, versioned static assets", () => {
		expect(urls.length).toBeGreaterThan(0)
		for (const url of urls) {
			expect(url.startsWith("/assets/wahni_solar/field/")).toBe(true)
			expect(url.endsWith(".html")).toBe(false)
		}
	})
	it("has no navigation fallback and waits for the user before updating", () => {
		expect(source).not.toMatch(/createHandlerBoundToURL\(\s*"/)
		expect(source).toContain("SKIP_WAITING")
		expect(source).not.toMatch(/importScripts/)
	})
	it("ships a manifest scoped to /field", () => {
		const manifest = JSON.parse(fs.readFileSync(path.join(out, "manifest.webmanifest"), "utf8"))
		expect(manifest).toMatchObject({ id: "/field", scope: "/field", start_url: "/field", display: "standalone" })
	})
})
