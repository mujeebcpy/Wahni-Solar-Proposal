import { createApp } from "vue"
import App from "./App.vue"
import router from "./router"
import translation from "./plugins/translation"
import { captureInstallPrompt } from "./composables/useInstall"
import { installUnloadGuard } from "./composables/useDirty"
import { registerServiceWorker } from "./composables/useServiceWorker"
import { apiPost } from "./utils/api"
import "./main.css"

captureInstallPrompt()
installUnloadGuard()

async function boot() {
	if (!window.frappe?.boot) {
		// Vite dev server: field.html (with boot data) is rendered only by Frappe.
		try {
			window.frappe.boot = await apiPost("wahni_solar.field_portal.api.get_boot_for_dev")
		} catch {
			window.frappe.boot = {}
		}
	}
	const app = createApp(App)
	app.use(translation)
	app.use(router)
	await router.isReady()
	app.mount("#app")
	registerServiceWorker()
}

boot()
