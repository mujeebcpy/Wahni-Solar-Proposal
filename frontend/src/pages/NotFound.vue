<template>
	<EmptyState icon="compass" :title="__('Page not found')" :message="__('The page you opened does not exist.')">
		<RouterLink :to="{ name: 'Home' }" class="inline-flex min-h-touch items-center text-base font-medium text-brand-700 underline">
			{{ __("Go to Home") }}
		</RouterLink>
	</EmptyState>
</template>

<script setup>
import EmptyState from "@/components/EmptyState.vue"
import { __ } from "@/plugins/translation"
</script>
