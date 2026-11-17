<template>
	<div class="fixed inset-x-0 bottom-0 z-30 border-t border-gray-200 bg-white/95 pb-safe-bottom backdrop-blur">
		<p v-if="error" class="mx-auto max-w-3xl px-4 pt-2 text-sm text-red-700" role="alert">{{ error }}</p>
		<div class="mx-auto flex max-w-3xl items-center gap-2 px-4 py-2">
			<slot />
		</div>
	</div>
</template>

<script setup>
defineProps({ error: { type: String, default: "" } })
</script>
