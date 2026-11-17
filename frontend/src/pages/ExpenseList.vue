<template>
	<div>
		<div class="-mx-4 mb-3 overflow-x-auto px-4" role="tablist" :aria-label="__('Filter claims')">
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
			{{ error }}
			<button type="button" class="ml-2 underline" @click="load(true)">{{ __("Retry") }}</button>
		</p>

		<ul class="space-y-3" :aria-busy="loading">
			<li v-for="claim in claims" :key="claim.name">
				<RouterLink :to="{ name: 'Expense', params: { name: claim.name } }" class="block rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
					<div class="flex items-start justify-between gap-3">
						<div class="min-w-0">
							<p class="truncate text-base font-medium">{{ claim.expense_types.join(", ") || __("Expense claim") }}</p>
							<p class="text-sm text-gray-600">{{ formatDate(claim.posting_date) }} · {{ claim.name }}</p>
						</div>
						<p class="shrink-0 text-base font-semibold">{{ formatCurrency(claim.total_claimed_amount, claim.currency) }}</p>
					</div>
					<div class="mt-2 flex flex-wrap gap-2">
						<StatusBadge :label="claim.docstatus === 0 ? 'Draft' : claim.status" />
						<StatusBadge v-if="claim.approval_status !== 'Draft'" :label="claim.approval_status" />
					</div>
				</RouterLink>
			</li>
		</ul>

		<p v-if="loading" class="py-6 text-center text-sm text-gray-600" role="status">{{ __("Loading…") }}</p>
		<EmptyState v-else-if="!claims.length && !error" icon="credit-card" :title="__('No expense claims')" :message="__('Claims you create appear here.')" />
		<Button v-if="hasMore && !loading" class="mt-4 w-full min-h-touch" @click="load(false)">{{ __("Load more") }}</Button>

		<RouterLink
			:to="{ name: 'Expense', params: { name: 'new' } }"
			class="fixed bottom-[calc(5rem+env(safe-area-inset-bottom))] right-4 z-20 flex h-14 items-center gap-2 rounded-full bg-gray-900 px-5 text-white shadow-lg"
		>
			<FeatherIcon name="plus" class="h-5 w-5" aria-hidden="true" />
			<span class="text-base font-medium">{{ __("New claim") }}</span>
		</RouterLink>
	</div>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Button, FeatherIcon } from "frappe-ui"
import EmptyState from "@/components/EmptyState.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { __ } from "@/plugins/translation"
import { apiGet } from "@/utils/api"
import { formatCurrency, formatDate } from "@/utils/format"

const PAGE = 20
const filters = [
	{ value: "", label: "All" },
	{ value: "draft", label: "Draft" },
	{ value: "approved", label: "Approved" },
	{ value: "unpaid", label: "Unpaid" },
	{ value: "paid", label: "Paid" },
	{ value: "rejected", label: "Rejected" },
]
const route = useRoute()
const router = useRouter()
const status = ref(filters.some((f) => f.value === route.query.status) ? route.query.status : "")
const claims = ref([])
const loading = ref(false)
const error = ref("")
const hasMore = ref(false)

function setStatus(value) {
	status.value = value
	router.replace({ query: value ? { status: value } : {} })
	load(true)
}

async function load(reset) {
	loading.value = true
	error.value = ""
	try {
		const rows = await apiGet("wahni_solar.field_portal.expenses.list_claims", {
			status: status.value, start: reset ? 0 : claims.value.length, page_length: PAGE,
		})
		claims.value = reset ? rows : [...claims.value, ...rows]
		hasMore.value = rows.length === PAGE
	} catch (e) {
		error.value = e.message
	} finally {
		loading.value = false
	}
}

onMounted(() => load(true))
</script>
