import { computed, onBeforeUnmount, reactive, watch } from "vue"

// Forms register unsaved state here so updates/navigation can warn before discarding it.
const dirtyForms = reactive(new Set())

export const hasUnsavedChanges = computed(() => dirtyForms.size > 0)

export function useDirtyTracking(key, isDirty) {
	watch(isDirty, (dirty) => (dirty ? dirtyForms.add(key) : dirtyForms.delete(key)), { immediate: true })
	onBeforeUnmount(() => dirtyForms.delete(key))
}

export function installUnloadGuard() {
	window.addEventListener("beforeunload", (event) => {
		if (!dirtyForms.size) return
		event.preventDefault()
		event.returnValue = ""
	})
}

// After the user explicitly agrees to discard edits (e.g. logout).
export function clearDirty() {
	dirtyForms.clear()
}
