<template>
	<div class="flex min-h-[100dvh] flex-col">
		<header class="sticky top-0 z-30 border-b border-gray-200 bg-white pt-safe-top">
			<div class="mx-auto flex h-14 max-w-3xl items-center gap-2 px-safe-left pl-3 pr-1">
				<button
					v-if="showBack"
					type="button"
					class="flex min-h-touch min-w-touch items-center justify-center rounded text-gray-700"
					:aria-label="__('Back')"
					@click="goBack"
				>
					<FeatherIcon name="chevron-left" class="h-6 w-6" aria-hidden="true" />
				</button>
				<RouterLink v-else :to="{ name: 'Home' }" class="flex min-h-touch items-center" :aria-label="__('Wahni Field home')">
					<BrandMark size="sm" />
				</RouterLink>
				<h1 class="flex-1 truncate text-lg font-semibold">{{ title }}</h1>
				<HeaderMenu />
			</div>
		</header>

		<main id="main" class="mx-auto w-full max-w-3xl flex-1 px-4 py-4" :class="{ 'pb-nav': !route.meta?.hideNav }">
			<RouterView />
		</main>

		<BottomNav v-if="!route.meta?.hideNav" />
	</div>
</template>

<script setup>
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@/plugins/translation"
import BrandMark from "@/components/BrandMark.vue"
import BottomNav from "@/components/BottomNav.vue"
import HeaderMenu from "@/components/HeaderMenu.vue"

const route = useRoute()
const router = useRouter()

const TAB_ROOTS = ["Home", "SiteVisits", "PMSVisits", "Expenses"]
const showBack = computed(() => !TAB_ROOTS.includes(route.name))
const title = computed(() => {
	if (route.params.name === "new" && route.meta?.title) return __("New {0}", [__(route.meta.title)])
	return route.meta?.title ? __(route.meta.title) : __("Wahni Field")
})

function goBack() {
	// Deep links have no in-app history; fall back to the section list.
	if (window.history.state?.back) router.back()
	else router.push(fallbackFor(route.meta?.tab))
}

function fallbackFor(tab) {
	return { "site-visits": { name: "SiteVisits" }, pms: { name: "PMSVisits" }, expenses: { name: "Expenses" } }[tab] || { name: "Home" }
}
</script>
