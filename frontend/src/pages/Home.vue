<template>
	<div class="space-y-6">
		<section>
			<p class="text-sm text-gray-600">{{ greeting }}</p>
			<h2 class="text-xl font-semibold">{{ employee?.employee_name || session.info?.full_name }}</h2>
		</section>

		<section :aria-label="__('Quick actions')">
			<h3 class="mb-2 text-sm font-medium uppercase tracking-wide text-gray-600">{{ __("Quick actions") }}</h3>
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
				<RouterLink
					v-for="action in actions"
					:key="action.label"
					:to="{ name: action.route, params: action.params }"
					class="flex min-h-[64px] items-center gap-3 rounded-lg border border-gray-200 bg-white px-4 shadow-sm"
				>
					<span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-50">
						<FeatherIcon :name="action.icon" class="h-5 w-5 text-brand-700" aria-hidden="true" />
					</span>
					<span class="text-base font-medium">{{ __(action.label) }}</span>
				</RouterLink>
			</div>
		</section>

		<section :aria-label="__('Open work')">
			<h3 class="mb-2 text-sm font-medium uppercase tracking-wide text-gray-600">{{ __("Open work") }}</h3>
			<p v-if="summaryError" class="rounded bg-red-50 p-3 text-sm text-red-800" role="alert">
				{{ summaryError }} <button type="button" class="ml-2 underline" @click="loadSummary">{{ __("Retry") }}</button>
			</p>
			<div v-else class="grid grid-cols-3 gap-2">
				<RouterLink v-for="tile in tiles" :key="tile.label" :to="tile.to" class="rounded-lg border border-gray-200 bg-white p-3 text-center">
					<span class="block text-2xl font-semibold">{{ summary ? tile.count : "–" }}</span>
					<span class="block text-xs text-gray-700">{{ __(tile.label) }}</span>
				</RouterLink>
			</div>
			<ul v-if="summary?.recent.length" class="mt-3 divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
				<li v-for="item in summary.recent" :key="item.name">
					<RouterLink :to="{ name: item.doctype === 'Site Visit' ? 'SiteVisit' : 'PMSVisit', params: { name: item.name } }" class="flex min-h-[56px] items-center justify-between gap-3 px-4">
						<span class="min-w-0">
							<span class="block truncate text-base">{{ item.title }}</span>
							<span class="block text-xs text-gray-600">{{ __(item.doctype) }} · {{ item.name }}</span>
						</span>
						<StatusBadge :label="item.status" />
					</RouterLink>
				</li>
			</ul>
		</section>

		<section v-if="!installed" class="rounded-lg border border-brand-100 bg-brand-50 p-4">
			<p class="text-base font-medium">{{ __("Install Wahni Field") }}</p>
			<p class="mt-1 text-sm text-gray-700">{{ __("Add it to your home screen for quick access.") }}</p>
			<RouterLink :to="{ name: 'Install' }" class="mt-2 inline-flex min-h-touch items-center text-sm font-medium text-brand-700 underline">
				{{ __("How to install") }}
			</RouterLink>
		</section>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { apiGet } from "@/utils/api"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@/plugins/translation"
import { session } from "@/data/session"
import { useInstall } from "@/composables/useInstall"

const { installed } = useInstall()
const employee = computed(() => session.info?.employee)
const actions = [
	{ route: "SiteVisit", params: { name: "new" }, icon: "map-pin", label: "New Site Visit" },
	{ route: "PMSVisit", params: { name: "new" }, icon: "tool", label: "New PMS Visit" },
	{ route: "Expense", params: { name: "new" }, icon: "credit-card", label: "New Expense Claim" },
]
const summary = ref(null)
const summaryError = ref("")
const tiles = computed(() => [
	{ label: "Site visits", count: summary.value?.counts["Site Visit"] ?? 0, to: { name: "SiteVisits" } },
	{ label: "PMS visits", count: summary.value?.counts["PMS Visit"] ?? 0, to: { name: "PMSVisits" } },
	{ label: "Draft claims", count: summary.value?.counts["Expense Claim"] ?? 0, to: { name: "Expenses", query: { status: "draft" } } },
])

async function loadSummary() {
	summaryError.value = ""
	try {
		summary.value = await apiGet("wahni_solar.field_portal.api.get_home_summary")
	} catch (e) {
		summaryError.value = e.message
	}
}
onMounted(loadSummary)

const greeting = computed(() => {
	const hour = new Date().getHours()
	return hour < 12 ? __("Good morning") : hour < 17 ? __("Good afternoon") : __("Good evening")
})
</script>
