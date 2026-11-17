<template>
	<div :ref="(el) => $emit('mounted', el)">
		<template v-if="!field.supported">
			<p class="text-xs text-gray-600">{{ field.label }}</p>
			<p class="text-sm text-amber-800">{{ __("This field can only be edited in Desk.") }}</p>
		</template>

		<label v-else-if="field.fieldtype === 'Check'" class="flex min-h-touch items-center gap-3">
			<input :id="id" type="checkbox" class="h-5 w-5" :checked="!!modelValue" :disabled="readOnly" @change="emit('update:modelValue', $event.target.checked ? 1 : 0)" />
			<span class="text-base">{{ field.label }}</span>
		</label>

		<template v-else>
			<label :for="id" class="mb-1.5 block text-xs text-gray-600">
				{{ field.label }}<span v-if="required" class="text-red-600" aria-hidden="true"> *</span>
				<span v-if="required" class="sr-only">({{ __("required") }})</span>
			</label>

			<div v-if="readOnly" :id="id" class="min-h-[2rem] whitespace-pre-line break-words text-base text-gray-900">
				<a v-if="isPhone && modelValue" :href="`tel:${modelValue}`" class="underline">{{ modelValue }}</a>
				<a v-else-if="link" :href="link" target="_blank" rel="noopener" class="underline">{{ modelValue }}</a>
				<GeoField v-else-if="field.fieldtype === 'Geolocation'" :model-value="modelValue" read-only />
				<span v-else>{{ display || "—" }}</span>
			</div>

			<select
				v-else-if="field.fieldtype === 'Select'"
				:id="id"
				class="min-h-touch w-full rounded border bg-white px-3"
				:class="error ? 'border-red-500' : 'border-gray-300'"
				:value="modelValue ?? ''"
				:aria-invalid="!!error"
				:aria-describedby="describedBy"
				@change="emit('update:modelValue', $event.target.value || null)"
			>
				<option v-for="option in selectOptions" :key="option" :value="option">{{ option ? __(option) : __("Select") }}</option>
			</select>

			<textarea
				v-else-if="isText"
				:id="id"
				rows="3"
				class="w-full rounded border px-3 py-2"
				:class="error ? 'border-red-500' : 'border-gray-300'"
				:value="modelValue ?? ''"
				:aria-invalid="!!error"
				:aria-describedby="describedBy"
				@input="emit('update:modelValue', $event.target.value)"
			/>

			<GeoField v-else-if="field.fieldtype === 'Geolocation'" :model-value="modelValue" @update:model-value="(v) => emit('update:modelValue', v)" />

			<SearchSelect
				v-else-if="field.fieldtype === 'Link'"
				:model-value="modelValue"
				:label="field.label"
				:search="searchLink"
				:error="error"
				@update:model-value="(v) => emit('update:modelValue', v)"
			/>

			<input
				v-else
				:id="id"
				:type="inputType"
				:inputmode="inputMode"
				:step="numeric ? 'any' : undefined"
				class="min-h-touch w-full rounded border px-3"
				:class="error ? 'border-red-500' : 'border-gray-300'"
				:value="modelValue ?? ''"
				:aria-invalid="!!error"
				:aria-describedby="describedBy"
				@input="onInput"
			/>
			<button
				v-if="isLocationLink && !readOnly"
				type="button"
				class="mt-2 inline-flex min-h-touch items-center gap-1 text-sm underline"
				:disabled="locating"
				@click="fillLocationLink"
			>
				<FeatherIcon name="crosshair" class="h-4 w-4" aria-hidden="true" />{{ locating ? __("Locating…") : __("Use my current location") }}
			</button>
			<p v-if="locationError" class="mt-1 text-sm text-red-700" role="alert">{{ locationError }}</p>
			<p v-if="field.description && !readOnly" :id="`${id}-help`" class="mt-1 text-xs text-gray-600">{{ field.description }}</p>
			<p v-if="error" :id="`${id}-error`" class="mt-1 text-sm text-red-700">{{ error }}</p>
		</template>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import GeoField from "@/components/GeoField.vue"
import SearchSelect from "@/components/SearchSelect.vue"
import { __ } from "@/plugins/translation"
import { apiGet } from "@/utils/api"
import { formatDate } from "@/utils/format"
import { safeHttpUrl } from "@/utils/geo"

const props = defineProps({
	field: { type: Object, required: true },
	modelValue: { default: null },
	required: Boolean,
	readOnly: Boolean,
	error: { type: String, default: "" },
})
const emit = defineEmits(["update:modelValue", "mounted"])
const id = `field-${props.field.fieldname}`

const numeric = computed(() => ["Int", "Float", "Currency", "Percent"].includes(props.field.fieldtype))
const isText = computed(() => ["Small Text", "Text", "Long Text"].includes(props.field.fieldtype))
const isPhone = computed(() => props.field.fieldtype === "Phone" || /phone|mobile|contact_number/.test(props.field.fieldname))
const inputType = computed(() => (numeric.value ? "number" : props.field.fieldtype === "Date" ? "date" : isPhone.value ? "tel" : "text"))
const inputMode = computed(() => (props.field.fieldtype === "Int" ? "numeric" : numeric.value ? "decimal" : isPhone.value ? "tel" : undefined))
const selectOptions = computed(() => {
	const options = (props.field.options || "").split("\n")
	return options.includes("") ? options : ["", ...options]
})
const link = computed(() => (/link|url/.test(props.field.fieldname) ? safeHttpUrl(props.modelValue) : null))
const display = computed(() => {
	const value = props.modelValue
	if (value === null || value === undefined || value === "") return ""
	if (props.field.fieldtype === "Date") return formatDate(value)
	if (props.field.fieldtype === "Percent") return `${value}%`
	return __(String(value))
})
const describedBy = computed(() => [props.error && `${id}-error`, props.field.description && `${id}-help`].filter(Boolean).join(" ") || undefined)

const isLocationLink = computed(() => props.field.fieldtype === "Data" && /location_link/.test(props.field.fieldname))
const locating = ref(false)
const locationError = ref("")

// A maps link from one explicit location reading (never continuous tracking).
function fillLocationLink() {
	locationError.value = ""
	if (!navigator.geolocation) {
		locationError.value = __("Location is not available on this device. Paste a maps link instead.")
		return
	}
	locating.value = true
	navigator.geolocation.getCurrentPosition(
		({ coords }) => {
			locating.value = false
			emit("update:modelValue", `https://www.google.com/maps?q=${coords.latitude.toFixed(6)},${coords.longitude.toFixed(6)}`)
		},
		(error) => {
			locating.value = false
			locationError.value = error.code === 1 ? __("Location permission was denied. Paste a maps link instead.") : __("Could not get your location. Try again or paste a maps link.")
		},
		{ enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
	)
}

function onInput(event) {
	const raw = event.target.value
	if (!numeric.value) return emit("update:modelValue", raw)
	emit("update:modelValue", raw === "" ? null : Number(raw))
}

async function searchLink(txt, start, pageLength) {
	const rows = await apiGet("frappe.desk.search.search_link", {
		doctype: props.field.options, txt, page_length: pageLength,
	})
	return (rows || []).map((row) => ({ value: row.value, label: row.label || row.value, description: row.description }))
}
</script>
