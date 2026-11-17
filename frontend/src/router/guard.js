import { safeRedirect } from "@/utils/redirect"

export const PUBLIC_ROUTES = ["Login", "ForgotPassword"]

// Pure navigation decision: returns a redirect location or null to continue.
export function decideNavigation(to, { loggedIn, info }) {
	const isPublic = PUBLIC_ROUTES.includes(to.name)
	if (!loggedIn) {
		if (isPublic) return null
		const redirect = to.fullPath && to.fullPath !== "/" ? { redirect: to.fullPath } : {}
		return { name: "Login", query: redirect }
	}
	if (!info || !info.allowed) {
		return to.name === "AccessDenied" ? null : { name: "AccessDenied" }
	}
	if (isPublic || to.name === "AccessDenied") {
		return safeRedirect(to.query?.redirect) || { name: "Home" }
	}
	return null
}
