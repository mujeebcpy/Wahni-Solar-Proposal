import { ref } from "vue"
import { hasUnsavedChanges } from "./useDirty"

export const WORKER_URL = "/field/sw.js"
export const WORKER_SCOPE = "/field" // allowed by the Service-Worker-Allowed header

const updateAvailable = ref(false)
let waitingWorker = null

function watchForUpdate(registration) {
	if (registration.waiting && navigator.serviceWorker.controller) {
		waitingWorker = registration.waiting
		updateAvailable.value = true
	}
	registration.addEventListener("updatefound", () => {
		const worker = registration.installing
		worker?.addEventListener("statechange", () => {
			// Only an *update* waits; the first install has no controller.
			if (worker.state === "installed" && navigator.serviceWorker.controller) {
				waitingWorker = worker
				updateAvailable.value = true
			}
		})
	})
}

export async function registerServiceWorker() {
	if (!("serviceWorker" in navigator) || !import.meta.env.PROD) return null
	try {
		const registration = await navigator.serviceWorker.register(WORKER_URL, { scope: WORKER_SCOPE })
		watchForUpdate(registration)
		// Check for a new deployment when the app returns to the foreground.
		document.addEventListener("visibilitychange", () => {
			if (document.visibilityState === "visible") registration.update().catch(() => {})
		})
		return registration
	} catch (error) {
		console.warn("Wahni Field worker registration failed", error)
		return null
	}
}

export function useServiceWorker() {
	function applyUpdate() {
		if (!waitingWorker) return false
		if (hasUnsavedChanges.value) return false
		let reloaded = false
		navigator.serviceWorker.addEventListener("controllerchange", () => {
			if (reloaded) return
			reloaded = true
			window.location.reload()
		})
		waitingWorker.postMessage({ type: "SKIP_WAITING" })
		return true
	}
	return { updateAvailable, hasUnsavedChanges, applyUpdate }
}
