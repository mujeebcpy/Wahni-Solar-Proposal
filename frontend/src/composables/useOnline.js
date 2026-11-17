import { ref } from "vue"

const online = ref(typeof navigator === "undefined" ? true : navigator.onLine)
window.addEventListener("online", () => (online.value = true))
window.addEventListener("offline", () => (online.value = false))

export function useOnline() {
	return online
}
