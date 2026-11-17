// Small Frappe API client: CSRF, uniform errors and session-expiry detection.
import { reactive } from "vue"

export const connection = reactive({ sessionExpired: false })
export const SESSION_EXPIRED = "Your session has expired. Log in again, then save. Nothing was saved."

export class ApiError extends Error {
	constructor(message, { status = 0, excType = null, messages = [], network = false } = {}) {
		super(message)
		this.status = status
		this.excType = excType
		this.messages = messages.length ? messages : [message]
		this.network = network
		this.sessionExpired = false
	}
}

export function sessionUser() {
	const cookies = new URLSearchParams(document.cookie.split("; ").join("&"))
	const user = cookies.get("user_id")
	return user && user !== "Guest" ? user : null
}

function methodUrl(method) {
	return method.startsWith("/") ? method : `/api/method/${method}`
}

function parseServerMessages(data) {
	let messages = []
	try {
		messages = JSON.parse(data._server_messages || "[]").map((m) => {
			try {
				return JSON.parse(m).message
			} catch {
				return m
			}
		})
	} catch {
		messages = []
	}
	if (!messages.length && typeof data.message === "string") messages.push(data.message)
	if (data.exception && !messages.length) messages.push(String(data.exception).split(": ").slice(1).join(": "))
	if (data._error_message) messages.push(data._error_message)
	return messages.filter(Boolean).map(stripHtml)
}

export function stripHtml(text) {
	const div = document.createElement("div")
	div.innerHTML = String(text)
	return div.textContent || div.innerText || ""
}

async function request(httpMethod, method, payload) {
	let url = methodUrl(method)
	const headers = { Accept: "application/json", "X-Frappe-Site-Name": window.location.hostname }
	const init = { method: httpMethod, headers, credentials: "same-origin" }
	if (httpMethod === "GET") {
		const query = new URLSearchParams()
		for (const [key, value] of Object.entries(payload || {})) {
			if (value === undefined || value === null) continue
			query.set(key, typeof value === "object" ? JSON.stringify(value) : value)
		}
		if ([...query].length) url += `?${query}`
	} else {
		headers["Content-Type"] = "application/json; charset=utf-8"
		if (window.csrf_token && window.csrf_token !== "{{ csrf_token }}") {
			headers["X-Frappe-CSRF-Token"] = window.csrf_token
		}
		init.body = JSON.stringify(payload || {})
	}
	let response
	try {
		response = await fetch(url, init)
	} catch {
		throw new ApiError("You appear to be offline. Nothing was saved.", { network: true })
	}
	let data = {}
	try {
		data = await response.json()
	} catch {
		data = {}
	}
	if (response.ok) return data
	const messages = parseServerMessages(data)
	const error = new ApiError(messages[0] || `Request failed (${response.status})`, {
		status: response.status,
		excType: data.exc_type,
		messages,
	})
	if ([401, 403].includes(response.status) && method !== "login") {
		error.sessionExpired = await checkSessionExpired()
		if (error.sessionExpired) {
			error.message = SESSION_EXPIRED
			error.messages = [SESSION_EXPIRED]
		}
	}
	throw error
}

async function checkSessionExpired() {
	try {
		const response = await fetch(methodUrl("frappe.auth.get_logged_user"), {
			headers: { Accept: "application/json" },
			credentials: "same-origin",
		})
		const expired = !response.ok
		if (expired) connection.sessionExpired = true
		return expired
	} catch {
		return false
	}
}

export async function apiGet(method, params) {
	return (await request("GET", method, params)).message
}

export async function apiPost(method, args) {
	return (await request("POST", method, args)).message
}

// Raw response (e.g. /api/method/login returns fields outside "message").
export async function apiPostRaw(method, args) {
	return request("POST", method, args)
}

export async function refreshCsrfToken() {
	window.csrf_token = await apiGet("wahni_solar.field_portal.api.get_csrf_token")
}
