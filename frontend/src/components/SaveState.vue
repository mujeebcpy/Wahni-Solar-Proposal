<template>
	<p class="flex items-center gap-1.5 text-sm" :class="tone" role="status" aria-live="polite">
		<FeatherIcon :name="icon" class="h-4 w-4" aria-hidden="true" />
		<span>{{ text }}</span>
	</p>
</template>

<script setup>
import { computed } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@/plugins/translation"

// state: "saved" | "dirty" | "saving" | "uploading" | "error" | "new"
const props = defineProps({ state: { type: String, required: true } })
const MAP = {
	new: ["edit-3", "text-gray-600", "Not saved yet"],
	saved: ["check", "text-green-700", "All changes saved"],
	dirty: ["alert-circle", "text-amber-700", "Unsaved changes"],
	saving: ["loader", "text-gray-700", "Saving…"],
	uploading: ["upload-cloud", "text-gray-700", "Uploading…"],
	error: ["alert-triangle", "text-red-700", "Not saved"],
}
const icon = computed(() => MAP[props.state][0])
const tone = computed(() => MAP[props.state][1])
const text = computed(() => __(MAP[props.state][2]))
</script>
