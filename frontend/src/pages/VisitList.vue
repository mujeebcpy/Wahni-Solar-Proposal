<template>
	<div>
		<input
			v-model="txt"
			type="search"
			class="mb-3 min-h-touch w-full rounded border border-gray-300 bg-white px-3"
			:placeholder="__('Search customer, place or ID')"
			:aria-label="__('Search visits')"
			@input="onSearch"
		/>
		<div class="chip-scroll -mx-4 mb-2 px-4" role="tablist" :aria-label="__('Filter visits')">
			<div class="flex gap-2">
				<button
					v-for="filter in filters"
					:key="filter.value"
					type="button"
					role="tab"
					:aria-selected="status === filter.value"
					class="min-h-touch shrink-0 rounded-full border px-4 text-sm"
					:class="status === filter.value ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-300 bg-white text-gray-800'"
					@click="setStatus(filter.value)"
				>
					{{ __(filter.label) }}
				</button>
			</div>
		</div>

		<p v-if="error" class="mb-3 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">
			{{ error }} <button type="button" class="ml-2 underline" @click="load(true)">{{ __("Retry") }}</button>
		</p>

		<ul class="space-y-3" :aria-busy="loading">
			<li v-for="visit in visits" :key="visit.name">
				<RouterLink :to="{ name: config.formRoute, params: { name: visit.name } }" class="block rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
					<div class="flex items-start justify-between gap-3">
						<div class="min-w-0">
							<p class="truncate text-base font-medium">{{ config.title(visit) }}</p>
							<p class="truncate text-sm text-gray-600">{{ config.subtitle(visit) }}</p>
						</div>
						<StatusBadge :label="visit.status" />
					</div>
					<p class="mt-1 text-xs text-gray-600">{{ visit.name }} · {{ __("Updated {0}", [formatDate(visit.modified)]) }}</p>
				</RouterLink>
			</li>
		</ul>
		<p v-if="loading" class="py-6 text-center text-sm text-gray-600" role="status">{{ __("Loading…") }}</p>
		<EmptyState v-else-if="!visits.length && !error" :icon="config.icon" :title="__('No visits here')" :message="__('Visits assigned to you by the office, or created by you, appear here.')" />
		<Button v-if="hasMore && !loading" class="mt-4 w-full min-h-touch" @click="load(false)">{{ __("Load more") }}</Button>

		<RouterLink
			:to="{ name: config.formRoute, params: { name: 'new' } }"
			class="fixed bottom-[calc(5rem+env(safe-area-inset-bottom))] right-4 z-20 flex h-14 items-center gap-2 rounded-full bg-gray-900 px-5 text-white shadow-lg"
		>
			<FeatherIcon name="plus" class="h-5 w-5" aria-hidden="true" />
			<span class="text-base font-medium">{{ __("New visit") }}</span>
		</RouterLink>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Button, FeatherIcon } from "frappe-ui"
import EmptyState from "@/components/EmptyState.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { __ } from "@/plugins/translation"
import { apiGet } from "@/utils/api"
import { formatDate } from "@/utils/format"
import { VISIT_TYPES } from "@/utils/visitTypes"

const PAGE = 20
const filters = [
	{ value: "open", label: "Open" },
	{ value: "Assigned", label: "Assigned" },
	{ value: "In Progress", label: "In Progress" },
	{ value: "Completed", label: "Completed" },
	{ value: "", label: "All" },
]
const route = useRoute()
const router = useRouter()
const config = computed(() => VISIT_TYPES[route.meta.doctype])
const status = ref(filters.some((f) => f.value === route.query.status) ? route.query.status : "open")
const txt = ref(route.query.q || "")
const visits = ref([])
const loading = ref(false)
const error = ref("")
const hasMore = ref(false)
let timer = null
let requestId = 0

function setStatus(value) {
	status.value = value
	syncQuery()
	load(true)
}

function onSearch() {
	clearTimeout(timer)
	timer = setTimeout(() => {
		syncQuery()
		load(true)
	}, 300)
}

function syncQuery() {
	router.replace({ query: { ...(status.value !== "open" ? { status: status.value } : {}), ...(txt.value ? { q: txt.value } : {}) } })
}

async function load(reset) {
	const current = ++requestId
	loading.value = true
	error.value = ""
	try {
		const rows = await apiGet("wahni_solar.field_portal.visits.list_visits", {
			doctype: route.meta.doctype, status: status.value, txt: txt.value || undefined,
			start: reset ? 0 : visits.value.length, page_length: PAGE,
		})
		if (current !== requestId) return
		visits.value = reset ? rows : [...visits.value, ...rows]
		hasMore.value = rows.length === PAGE
	} catch (e) {
		if (current === requestId) error.value = e.message
	} finally {
		if (current === requestId) loading.value = false
	}
}

watch(() => route.meta.doctype, () => load(true), { immediate: true })
</script>
