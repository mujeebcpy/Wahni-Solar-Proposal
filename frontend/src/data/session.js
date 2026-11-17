import { reactive } from "vue"
import { apiGet, apiPost, apiPostRaw, connection, refreshCsrfToken, sessionUser } from "@/utils/api"

export const session = reactive({
	user: sessionUser(),
	info: null,
	infoError: null,
})

let infoPromise = null

export function isLoggedIn() {
	return !!session.user
}

export async function loadSessionInfo({ force = false } = {}) {
	if (!session.user) return null
	if (session.info && !force) return session.info
	if (!infoPromise || force) {
		infoPromise = apiGet("wahni_solar.field_portal.api.get_session_info")
			.then((info) => {
				session.info = info
				session.infoError = null
				return info
			})
			.catch((error) => {
				session.infoError = error
				if (error.sessionExpired || error.status === 401) session.user = null
				throw error
			})
			.finally(() => {
				infoPromise = null
			})
	}
	return infoPromise
}

// Returns {status: "ok" | "otp" | "password_reset" | "standard_login", ...}
export async function handleLoginResponse(response) {
	if (response.verification) {
		if (response.verification.setup) {
			return { status: "otp", tmpId: response.tmp_id, prompt: response.verification.prompt }
		}
		return { status: "standard_login" }
	}
	if (response.message === "Password Reset") {
		return { status: "password_reset", link: response.redirect_to }
	}
	if (response.message === "Logged In" || response.home_page) {
		session.user = sessionUser()
		session.info = null
		connection.sessionExpired = false
		await refreshCsrfToken()
		await loadSessionInfo({ force: true })
		return { status: "ok" }
	}
	return { status: "error" }
}

export async function login(usr, pwd) {
	return handleLoginResponse(await apiPostRaw("login", { usr, pwd }))
}

export async function verifyOtp(tmpId, otp) {
	return handleLoginResponse(await apiPostRaw("login", { tmp_id: tmpId, otp }))
}

export async function logout() {
	try {
		await apiPost("logout")
	} finally {
		// Full reload clears every in-memory form and cached response.
		session.user = null
		session.info = null
		window.location.replace("/field/login")
	}
}
