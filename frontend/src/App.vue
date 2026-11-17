<template>
	<div class="min-h-[100dvh] bg-gray-50 text-gray-900">
		<StatusBanners />
		<RouterView />
		<SessionExpiredDialog />
	</div>
</template>

<script setup>
import StatusBanners from "@/components/StatusBanners.vue"
import SessionExpiredDialog from "@/components/SessionExpiredDialog.vue"
</script>
