// Safe subset of Frappe depends_on expressions — never evaluated as JavaScript.
// Supported: "fieldname", "eval:doc.f", "eval:!doc.f", "eval:!!doc.f",
// "eval:doc.f == 'x'" / "!=" (and === / !==), joined with && or || (no parentheses).
// Returns {supported, value}; callers fall back to "visible"/"not required" and the
// server stays authoritative when an expression is unsupported.
const TERM_COMPARE = /^doc\.(\w+)\s*(===|==|!==|!=)\s*(['"])(.*)\3$/
const TERM_TRUTHY = /^(!{0,2})doc\.(\w+)$/
const PLAIN_FIELD = /^\w+$/

function empty(value) {
	return value === null || value === undefined || value === "" || value === 0 || value === false
}

function term(text, doc) {
	const t = text.trim()
	let m = t.match(TERM_COMPARE)
	if (m) {
		const actual = doc[m[1]] ?? ""
		const equal = String(actual) === m[4]
		return { supported: true, value: m[2].startsWith("!") ? !equal : equal }
	}
	m = t.match(TERM_TRUTHY)
	if (m) {
		// "__islocal" is always false here: the portal edits saved records only.
		const truthy = m[2] === "__islocal" ? false : !empty(doc[m[2]])
		return { supported: true, value: m[1] === "!" ? !truthy : truthy }
	}
	return { supported: false, value: true }
}

export function evaluateCondition(expression, doc) {
	if (!expression) return { supported: true, value: true }
	const expr = expression.trim()
	if (!expr.startsWith("eval:")) {
		return PLAIN_FIELD.test(expr) ? { supported: true, value: !empty(doc[expr]) } : { supported: false, value: true }
	}
	const body = expr.slice(5).trim()
	if (/[()]/.test(body) || (body.includes("&&") && body.includes("||"))) return { supported: false, value: true }
	const op = body.includes("||") ? "||" : "&&"
	const results = body.split(op).map((part) => term(part, doc))
	if (results.some((r) => !r.supported)) return { supported: false, value: true }
	const value = op === "||" ? results.some((r) => r.value) : results.every((r) => r.value)
	return { supported: true, value }
}

export function isVisible(field, doc) {
	return evaluateCondition(field.depends_on, doc).value
}

export function isEmptyValue(value) {
	return value === null || value === undefined || (typeof value === "string" && !value.trim())
}

// Fields that must have a value before the visit can be completed.
export function completionRequired(field, doc) {
	if (field.reqd) return true
	if (!field.mandatory_depends_on) return false
	const result = evaluateCondition(field.mandatory_depends_on, { ...doc, status: "Completed" })
	return result.supported && result.value
}

export function missingForCompletion(fields, doc) {
	return fields.filter((field) => field.supported !== false && completionRequired(field, doc) && isEmptyValue(doc[field.fieldname]))
}
