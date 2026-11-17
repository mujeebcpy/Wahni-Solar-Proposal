import { computed, reactive } from "vue"

// Captured as early as possible (main.js) because the event fires once.
const state = reactive({ deferredPrompt: null, installed: false })

export function captureInstallPrompt() {
	window.addEventListener("beforeinstallprompt", (event) => {
		event.preventDefault()
		state.deferredPrompt = event
	})
	window.addEventListener("appinstalled", () => {
		state.installed = true
		state.deferredPrompt = null
	})
}

export function isStandalone() {
	return window.matchMedia?.("(display-mode: standalone)").matches || window.navigator.standalone === true
}

export function isIOS(userAgent = navigator.userAgent, maxTouchPoints = navigator.maxTouchPoints) {
	// iPadOS 13+ reports itself as Macintosh with touch support.
	return /iphone|ipad|ipod/i.test(userAgent) || (/macintosh/i.test(userAgent) && maxTouchPoints > 1)
}

export function useInstall() {
	const canPrompt = computed(() => !!state.deferredPrompt)
	const installed = computed(() => state.installed || isStandalone())
	async function promptInstall() {
		if (!state.deferredPrompt) return false
		state.deferredPrompt.prompt()
		const { outcome } = await state.deferredPrompt.userChoice
		state.deferredPrompt = null
		return outcome === "accepted"
	}
	return { canPrompt, installed, ios: isIOS(), promptInstall }
}
