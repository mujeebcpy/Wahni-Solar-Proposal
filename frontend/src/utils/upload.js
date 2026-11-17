import { ApiError, SESSION_EXPIRED, connection } from "./api"

export const ACCEPTED_FILES = "image/*,application/pdf"
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024

export function validateFile(file, { imagesOnly = false } = {}) {
	if (imagesOnly && !file.type.startsWith("image/")) return "Choose a photo (image file)."
	if (!imagesOnly && !(file.type.startsWith("image/") || file.type === "application/pdf")) {
		return "Choose a photo or a PDF."
	}
	if (file.size > MAX_UPLOAD_BYTES) return "This file is larger than 10 MB."
	return null
}

// Private upload attached to a saved document. Returns {promise, abort}.
export function uploadFile({ file, doctype, docname, fieldname, onProgress }) {
	const xhr = new XMLHttpRequest()
	const promise = new Promise((resolve, reject) => {
		const form = new FormData()
		form.append("file", file, file.name)
		form.append("is_private", "1")
		form.append("doctype", doctype)
		form.append("docname", docname)
		if (fieldname) form.append("fieldname", fieldname)
		xhr.open("POST", "/api/method/upload_file")
		xhr.setRequestHeader("Accept", "application/json")
		if (window.csrf_token && window.csrf_token !== "{{ csrf_token }}") {
			xhr.setRequestHeader("X-Frappe-CSRF-Token", window.csrf_token)
		}
		xhr.upload.onprogress = (event) => {
			if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
		}
		xhr.onload = () => {
			let data = {}
			try {
				data = JSON.parse(xhr.responseText)
			} catch {
				data = {}
			}
			if (xhr.status >= 200 && xhr.status < 300 && data.message) return resolve(data.message)
			let message = `Upload failed (${xhr.status})`
			try {
				message = JSON.parse(JSON.parse(data._server_messages)[0]).message || message
			} catch {
				message = data.exception?.split(": ").slice(1).join(": ") || message
			}
			const error = new ApiError(message, { status: xhr.status, excType: data.exc_type })
			if (xhr.status === 403 || xhr.status === 401) {
				return fetch("/api/method/frappe.auth.get_logged_user", { credentials: "same-origin" }).then((r) => {
					if (!r.ok) {
						connection.sessionExpired = true
						error.message = SESSION_EXPIRED
					}
					reject(error)
				}, () => reject(error))
			}
			reject(error)
		}
		xhr.onerror = () => reject(new ApiError("Upload failed: check your connection and retry.", { network: true }))
		xhr.onabort = () => reject(new ApiError("Upload cancelled.", { network: false }))
		xhr.send(form)
	})
	return { promise, abort: () => xhr.abort() }
}
