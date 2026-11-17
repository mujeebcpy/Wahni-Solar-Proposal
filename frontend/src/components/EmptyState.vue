<template>
	<div class="flex flex-col items-center px-6 py-12 text-center">
		<div class="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-gray-100">
			<FeatherIcon :name="icon" class="h-6 w-6 text-gray-500" aria-hidden="true" />
		</div>
		<p class="text-base font-medium text-gray-900">{{ title }}</p>
		<p v-if="message" class="mt-1 text-sm text-gray-600">{{ message }}</p>
		<div v-if="$slots.default" class="mt-4"><slot /></div>
	</div>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
defineProps({
	icon: { type: String, default: "inbox" },
	title: { type: String, required: true },
	message: { type: String, default: "" },
})
</script>
