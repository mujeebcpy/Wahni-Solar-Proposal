<template>
	<div>
		<p class="mb-3 text-base text-gray-700">{{ __("Choose the Solar Proposal you are visiting. The visit will be assigned to you.") }}</p>
		<input
			v-model="txt"
			type="search"
			class="mb-3 min-h-touch w-full rounded border border-gray-300 bg-white px-3"
			:placeholder="__('Search proposal or customer')"
			:aria-label="__('Search proposals')"
			@input="onSearch"
		/>
		<p v-if="error" class="mb-3 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{{ error }}</p>
		<ul class="space-y-2">
			<li v-for="proposal in proposals" :key="proposal.name">
				<button
					type="button"
					class="flex min-h-[56px] w-full items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white px-4 text-left disabled:opacity-60"
					:disabled="!!creating"
					@click="create(proposal)"
				>
					<span class="min-w-0">
						<span class="block truncate text-base font-medium">{{ proposal.customer_name || proposal.name }}</span>
						<span class="block text-sm text-gray-600">{{ proposal.name }}</span>
					</span>
					<FeatherIcon :name="creating === proposal.name ? 'loader' : 'chevron-right'" class="h-5 w-5 text-gray-500" aria-hidden="true" />
				</button>
			</li>
		</ul>
		<p v-if="loading" class="py-6 text-center text-sm text-gray-600" role="status">{{ __("Loading…") }}</p>
		<EmptyState v-else-if="!proposals.length" icon="search" :title="__('No proposals found')" :message="__('Only proposals without a site visit are listed.')" />
		<Button v-if="hasMore && !loading" class="mt-4 w-full min-h-touch" @click="load(false)">{{ __("Load more") }}</Button>
	</div>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { Button, FeatherIcon } from "frappe-ui"
import EmptyState from "@/components/EmptyState.vue"
import { __ } from "@/plugins/translation"
import { apiGet, apiPost } from "@/utils/api"
import { newToken } from "@/utils/format"

const PAGE = 20
const router = useRouter()
const txt = ref("")
const proposals = ref([])
const loading = ref(false)
const error = ref("")
const hasMore = ref(false)
const creating = ref(null)
const tokens = {}
let timer = null
let requestId = 0

function onSearch() {
	clearTimeout(timer)
	timer = setTimeout(() => load(true), 300)
}

async function load(reset) {
	const current = ++requestId
	loading.value = true
	error.value = ""
	try {
		const rows = await apiGet("wahni_solar.field_portal.visits.search_proposals", {
			txt: txt.value, start: reset ? 0 : proposals.value.length, page_length: PAGE,
		})
		if (current !== requestId) return
		proposals.value = reset ? rows : [...proposals.value, ...rows]
		hasMore.value = rows.length === PAGE
	} catch (e) {
		if (current === requestId) error.value = e.message
	} finally {
		if (current === requestId) loading.value = false
	}
}

async function create(proposal) {
	if (creating.value) return
	creating.value = proposal.name
	error.value = ""
	// Same token on retry, so an uncertain first attempt cannot create a duplicate.
	tokens[proposal.name] ||= newToken()
	try {
		const result = await apiPost("wahni_solar.field_portal.visits.create_site_visit", {
			solar_proposal: proposal.name, client_token: tokens[proposal.name],
		})
		router.replace({ name: "SiteVisit", params: { name: result.name } })
	} catch (e) {
		error.value = e.message
	} finally {
		creating.value = null
	}
}

onMounted(() => load(true))
</script>
