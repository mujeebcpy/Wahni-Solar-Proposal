import dayjs from "dayjs"

export function formatCurrency(value, currency = "INR") {
	const amount = Number(value || 0)
	try {
		return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 2 }).format(amount)
	} catch {
		return `${currency} ${amount.toFixed(2)}`
	}
}

export function formatDate(value) {
	return value ? dayjs(value).format("DD MMM YYYY") : ""
}

export function today() {
	return dayjs().format("YYYY-MM-DD")
}

export function newToken() {
	if (window.crypto?.randomUUID) return window.crypto.randomUUID()
	return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function fileSize(bytes) {
	if (!bytes) return ""
	if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
	return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
