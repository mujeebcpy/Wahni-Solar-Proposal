<template>
	<nav
		class="fixed inset-x-0 bottom-0 z-30 border-t border-gray-200 bg-white pb-safe-bottom"
		:aria-label="__('Main')"
	>
		<ul class="mx-auto grid max-w-3xl grid-cols-4">
			<li v-for="tab in tabs" :key="tab.name">
				<RouterLink
					:to="{ name: tab.route }"
					class="flex min-h-[56px] flex-col items-center justify-center gap-0.5 text-xs"
					:class="active === tab.name ? 'font-semibold text-brand-700' : 'text-gray-600'"
					:aria-current="active === tab.name ? 'page' : undefined"
				>
					<FeatherIcon :name="tab.icon" class="h-5 w-5" aria-hidden="true" />
					<span>{{ __(tab.label) }}</span>
					<span v-if="active === tab.name" class="mt-0.5 h-0.5 w-6 rounded bg-brand-600" aria-hidden="true" />
				</RouterLink>
			</li>
		</ul>
	</nav>
</template>

<script setup>
import { computed } from "vue"
import { useRoute } from "vue-router"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@/plugins/translation"

const tabs = [
	{ name: "home", route: "Home", icon: "home", label: "Home" },
	{ name: "site-visits", route: "SiteVisits", icon: "map-pin", label: "Site Visits" },
	{ name: "pms", route: "PMSVisits", icon: "tool", label: "PMS" },
	{ name: "expenses", route: "Expenses", icon: "credit-card", label: "Expenses" },
]
const route = useRoute()
const active = computed(() => route.meta?.tab)
</script>
