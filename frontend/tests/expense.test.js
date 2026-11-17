import { describe, expect, it } from "vitest"
import { validateClaim } from "@/utils/expense"
import { targetSize } from "@/utils/image"
import { validateFile } from "@/utils/upload"
import { formatCurrency } from "@/utils/format"

const item = { expense_type: "Travel", amount: 10, expense_date: "2026-11-17" }

describe("validateClaim", () => {
	it("accepts a complete claim", () => {
		expect(validateClaim({ posting_date: "2026-11-17", expense_approver: "a@x", expenses: [item] }, { approverRequired: true })).toEqual({})
	})
	it("reports each problem against its field", () => {
		const errors = validateClaim(
			{ posting_date: "", expense_approver: null, expenses: [item, { ...item, amount: 0 }, { ...item, expense_type: null }] },
			{ approverRequired: true }
		)
		expect(Object.keys(errors).sort()).toEqual(["expense_approver", "expenses.1", "expenses.2", "posting_date"])
		expect(validateClaim({ posting_date: "x", expenses: [] }).expenses).toBeTruthy()
		expect(validateClaim({ posting_date: "x", expenses: [item] }, { approverRequired: false })).toEqual({})
	})
})

describe("uploads", () => {
	const file = (type, size) => ({ type, size, name: "f" })
	it("accepts photos and PDFs up to 10 MB", () => {
		expect(validateFile(file("image/jpeg", 1000))).toBeNull()
		expect(validateFile(file("application/pdf", 1000))).toBeNull()
		expect(validateFile(file("application/zip", 1000))).toBeTruthy()
		expect(validateFile(file("image/jpeg", 11 * 1024 * 1024))).toBeTruthy()
		expect(validateFile(file("application/pdf", 10), { imagesOnly: true })).toBeTruthy()
	})
	it("scales large photos but keeps detail", () => {
		expect(targetSize(4000, 3000)).toEqual({ width: 2400, height: 1800 })
		expect(targetSize(1200, 800)).toEqual({ width: 1200, height: 800 })
	})
})

describe("formatCurrency", () => {
	it("formats INR", () => {
		expect(formatCurrency(1234.5, "INR")).toMatch(/1,234\.5/)
	})
})
