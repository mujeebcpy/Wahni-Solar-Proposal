// Only in-app paths may be used as a post-login destination.
export function safeRedirect(value) {
	if (typeof value !== "string") return null
	if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return null
	if (/[\u0000-\u001f]/.test(value) || value.includes("\\")) return null
	if (/^\/[a-z][a-z0-9+.-]*:/i.test(value)) return null
	if (value === "/login" || value.startsWith("/login?")) return null
	return value
}
