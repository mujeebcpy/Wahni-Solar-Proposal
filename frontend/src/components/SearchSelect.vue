<template>
	<div>
		<label :for="id" class="mb-1.5 block text-xs text-gray-600">
			{{ label }}<span v-if="required" class="text-red-600" aria-hidden="true"> *</span>
		</label>
		<button
			:id="id"
			type="button"
			class="flex min-h-touch w-full items-center gap-2 rounded border bg-white px-3 text-left text-base"
			:class="error ? 'border-red-500' : 'border-gray-300'"
			:disabled="disabled"
			:aria-invalid="!!error"
			:aria-describedby="error ? `${id}-error` : undefined"
			@click="openSheet"
		>
			<span class="flex-1 truncate" :class="displayLabel ? 'text-gray-900' : 'text-gray-500'">
				{{ displayLabel || placeholder || __("Select") }}
			</span>
			<FeatherIcon v-if="!disabled" name="chevron-down" class="h-4 w-4 text-gray-500" aria-hidden="true" />
		</button>
		<p v-if="error" :id="`${id}-error`" class="mt-1 text-sm text-red-700">{{ error }}</p>

		<BottomSheet v-model="open" :title="label">
			<input
				v-model="query"
				type="search"
				class="mb-3 w-full rounded border border-gray-300 px-3 py-2"
				:placeholder="__('Search')"
				:aria-label="__('Search {0}', [label])"
				@input="onInput"
			/>
			<p v-if="loadError" class="mb-2 text-sm text-red-700" role="alert">
				{{ loadError }}
				<button type="button" class="ml-2 underline" @click="load(true)">{{ __("Retry") }}</button>
			</p>
			<ul role="listbox" :aria-label="label">
				<li v-if="!required && modelValue">
					<button type="button" class="option text-gray-600" @click="choose(null)">{{ __("Clear selection") }}</button>
				</li>
				<li v-for="option in options" :key="option.value">
					<button
						type="button"
						role="option"
						class="option"
						:aria-selected="option.value === modelValue"
						:class="{ 'bg-brand-50': option.value === modelValue }"
						@click="choose(option)"
					>
						<span class="block text-base">{{ option.label }}</span>
						<span v-if="option.description" class="block text-sm text-gray-600">{{ option.description }}</span>
					</button>
				</li>
			</ul>
			<p v-if="loading" class="py-4 text-center text-sm text-gray-600" role="status">{{ __("Loading…") }}</p>
			<p v-else-if="!options.length && !loadError" class="py-4 text-center text-sm text-gray-600">{{ __("No results") }}</p>
			<button v-if="hasMore && !loading" type="button" class="option text-center text-brand-700" @click="load(false)">
				{{ __("Load more") }}
			</button>
		</BottomSheet>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import BottomSheet from "@/components/BottomSheet.vue"
import { __ } from "@/plugins/translation"

const props = defineProps({
	modelValue: { type: String, default: null },
	label: { type: String, required: true },
	selectedLabel: { type: String, default: "" },
	placeholder: { type: String, default: "" },
	required: Boolean,
	disabled: Boolean,
	error: { type: String, default: "" },
	// (query, start) => Promise<[{value, label, description}]>
	search: { type: Function, required: true },
	pageLength: { type: Number, default: 20 },
})
const emit = defineEmits(["update:modelValue", "select"])

const id = `select-${Math.random().toString(36).slice(2)}`
const open = ref(false)
const query = ref("")
const options = ref([])
const loading = ref(false)
const loadError = ref("")
const hasMore = ref(false)
const picked = ref(null)
let timer = null
let requestId = 0

const displayLabel = computed(() => (picked.value?.value === props.modelValue ? picked.value.label : null) || props.selectedLabel || props.modelValue)

function openSheet() {
	open.value = true
	if (!options.value.length) load(true)
}

function onInput() {
	clearTimeout(timer)
	timer = setTimeout(() => load(true), 250)
}

async function load(reset) {
	const current = ++requestId
	loading.value = true
	loadError.value = ""
	try {
		const start = reset ? 0 : options.value.length
		const rows = await props.search(query.value, start, props.pageLength)
		if (current !== requestId) return // ignore stale responses
		options.value = reset ? rows : [...options.value, ...rows]
		hasMore.value = rows.length >= props.pageLength
	} catch (error) {
		if (current === requestId) loadError.value = error.message || __("Could not load options.")
	} finally {
		if (current === requestId) loading.value = false
	}
}

function choose(option) {
	picked.value = option
	emit("update:modelValue", option ? option.value : null)
	emit("select", option)
	open.value = false
}
</script>

<style scoped>
.option {
	@apply block min-h-touch w-full rounded px-3 py-2 text-left hover:bg-gray-50;
}
</style>
