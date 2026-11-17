<template>
	<div>
		<p class="mb-3 text-base text-gray-700">{{ __("Choose the completed Project for this maintenance visit. The visit will be assigned to you.") }}</p>
		<input
			v-model="txt"
			type="search"
			class="mb-3 min-h-touch w-full rounded border border-gray-300 bg-white px-3"
			:placeholder="__('Search project or customer')"
			:aria-label="__('Search projects')"
			@input="onSearch"
		/>
		<p v-if="error" class="mb-3 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{{ error }}</p>
		<ul class="space-y-2">
			<li v-for="project in projects" :key="project.name">
				<button
					type="button"
					class="flex min-h-[56px] w-full items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white px-4 text-left disabled:opacity-60"
					:disabled="!!creating"
					@click="create(project)"
				>
					<span class="min-w-0">
						<span class="block truncate text-base font-medium">{{ project.customer_name || project.project_name || project.name }}</span>
						<span class="block truncate text-sm text-gray-600">{{ project.project_name }} · {{ project.name }}</span>
					</span>
					<FeatherIcon :name="creating === project.name ? 'loader' : 'chevron-right'" class="h-5 w-5 text-gray-500" aria-hidden="true" />
				</button>
			</li>
		</ul>
		<p v-if="loading" class="py-6 text-center text-sm text-gray-600" role="status">{{ __("Loading…") }}</p>
		<EmptyState v-else-if="!projects.length" icon="search" :title="__('No completed projects found')" />
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
const projects = ref([])
const loading = ref(false)
const error = ref("")
const hasMore = ref(false)
const creating = ref(null)
// One token per screen visit: a retry after an uncertain failure cannot duplicate,
// while a deliberate second visit for the same Project is still possible later.
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
		const rows = await apiGet("wahni_solar.field_portal.visits.search_completed_projects", {
			txt: txt.value, start: reset ? 0 : projects.value.length, page_length: PAGE,
		})
		if (current !== requestId) return
		projects.value = reset ? rows : [...projects.value, ...rows]
		hasMore.value = rows.length === PAGE
	} catch (e) {
		if (current === requestId) error.value = e.message
	} finally {
		if (current === requestId) loading.value = false
	}
}

async function create(project) {
	if (creating.value) return
	creating.value = project.name
	error.value = ""
	tokens[project.name] ||= newToken()
	try {
		const result = await apiPost("wahni_solar.field_portal.visits.create_pms_visit", {
			project: project.name, client_token: tokens[project.name],
		})
		router.replace({ name: "PMSVisit", params: { name: result.name } })
	} catch (e) {
		error.value = e.message
	} finally {
		creating.value = null
	}
}

onMounted(() => load(true))
</script>
