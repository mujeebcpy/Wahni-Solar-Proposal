<template>
	<span class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium" :class="tone.classes">
		<FeatherIcon :name="tone.icon" class="h-3.5 w-3.5" aria-hidden="true" />
		{{ __(label) }}
	</span>
</template>

<script setup>
import { computed } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@/plugins/translation"

const props = defineProps({ label: { type: String, required: true } })
// Icon + text so status never depends on colour alone.
const TONES = {
	green: { classes: "bg-green-50 text-green-800", icon: "check-circle" },
	red: { classes: "bg-red-50 text-red-800", icon: "x-circle" },
	orange: { classes: "bg-amber-50 text-amber-800", icon: "clock" },
	blue: { classes: "bg-blue-50 text-blue-800", icon: "play-circle" },
	gray: { classes: "bg-gray-100 text-gray-800", icon: "edit-3" },
}
const STATUS_TONES = {
	Draft: "gray", Assigned: "orange", "In Progress": "blue", Completed: "green", Approved: "green", Paid: "green",
	Rejected: "red", Cancelled: "red", Unpaid: "orange", "Partially Paid": "orange", Submitted: "blue",
}
const tone = computed(() => TONES[STATUS_TONES[props.label] || "gray"])
</script>
