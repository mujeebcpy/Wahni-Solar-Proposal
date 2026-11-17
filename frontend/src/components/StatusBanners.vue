<template>
	<div class="sticky top-0 z-40" aria-live="polite">
		<div v-if="!online" role="status" class="flex items-center gap-2 bg-gray-900 px-4 py-2 pt-safe-top text-sm text-white">
			<FeatherIcon name="wifi-off" class="h-4 w-4 shrink-0" aria-hidden="true" />
			<span>{{ __("You are offline. Changes cannot be saved until you reconnect.") }}</span>
		</div>
		<div v-if="updateAvailable" role="status" class="flex items-center gap-3 bg-brand-50 px-4 py-2 text-sm text-gray-900 border-b border-brand-100">
			<FeatherIcon name="download" class="h-4 w-4 shrink-0 text-brand-700" aria-hidden="true" />
			<span class="flex-1">
				{{ hasUnsavedChanges ? __("An update is ready. Save your changes, then reload.") : __("A new version of Wahni Field is ready.") }}
			</span>
			<Button size="sm" variant="solid" :disabled="hasUnsavedChanges" class="min-h-touch" @click="applyUpdate">
				{{ __("Reload") }}
			</Button>
		</div>
	</div>
</template>

<script setup>
import { Button, FeatherIcon } from "frappe-ui"
import { useOnline } from "@/composables/useOnline"
import { useServiceWorker } from "@/composables/useServiceWorker"

const online = useOnline()
const { updateAvailable, hasUnsavedChanges, applyUpdate } = useServiceWorker()
</script>
