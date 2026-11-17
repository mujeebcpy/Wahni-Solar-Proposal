<template>
	<div class="pb-28">
		<p v-if="loadError" class="rounded bg-red-50 p-3 text-sm text-red-800" role="alert">
			{{ loadError }}
			<button type="button" class="ml-2 underline" @click="load">{{ __("Retry") }}</button>
		</p>
		<p v-else-if="!payload" class="py-10 text-center text-sm text-gray-600" role="status">{{ __("Loading…") }}</p>

		<template v-else>
			<div v-if="conflict" class="mb-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm" role="alert">
				<p>{{ conflict }}</p>
				<button type="button" class="mt-2 min-h-touch font-medium underline" @click="reloadLatest">{{ __("Discard my edits and load the latest") }}</button>
			</div>

			<!-- Source and assignment context, so office-prepared work is clear at a glance -->
			<section class="mb-4 rounded-lg border border-gray-200 bg-white p-4">
				<div class="flex items-start justify-between gap-2">
					<div class="min-w-0">
						<h2 class="truncate text-lg font-semibold">{{ title }}</h2>
						<p class="text-sm text-gray-600">{{ payload.name }}<template v-if="sourceLabel"> · {{ sourceLabel }}</template></p>
					</div>
					<StatusBadge :label="payload.status" />
				</div>
				<p v-if="subtitle" class="mt-2 whitespace-pre-line text-sm text-gray-800">{{ subtitle }}</p>
				<div class="mt-3 flex flex-wrap gap-2">
					<a v-for="phone in phones" :key="phone" :href="`tel:${phone}`" class="inline-flex min-h-touch items-center gap-1 rounded border border-gray-300 px-3 text-sm">
						<FeatherIcon name="phone" class="h-4 w-4" aria-hidden="true" />{{ phone }}
					</a>
					<a v-if="directions" :href="directions" target="_blank" rel="noopener" class="inline-flex min-h-touch items-center gap-1 rounded border border-gray-300 px-3 text-sm">
						<FeatherIcon name="navigation" class="h-4 w-4" aria-hidden="true" />{{ __("Directions") }}
					</a>
				</div>
				<p class="mt-2 text-xs text-gray-600">
					{{ __("Assigned to {0}", [payload.assignee_name || payload.assignee]) }}<template v-if="payload.owner !== sessionUser"> · {{ __("prepared by the office") }}</template>
				</p>
				<p v-if="!payload.editable" class="mt-2 rounded bg-gray-100 p-2 text-sm text-gray-800">
					{{ payload.status === "Completed" ? __("This visit is completed. Ask the office to reopen it if something must change.") : __("You can view this visit but not edit it.") }}
				</p>
			</section>

			<nav class="-mx-4 mb-4 overflow-x-auto px-4" :aria-label="__('Form steps')">
				<ol class="flex gap-2">
					<li v-for="(step, index) in allSteps" :key="step.key">
						<button
							type="button"
							class="flex min-h-touch shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 text-sm"
							:class="index === current ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-300 bg-white text-gray-800'"
							:aria-current="index === current ? 'step' : undefined"
							@click="goTo(index)"
						>
							<span>{{ index + 1 }}. {{ step.label }}</span>
							<span v-if="stepMissing(step.key)" class="rounded-full bg-red-100 px-1.5 text-xs text-red-800" :aria-label="__('{0} missing', [stepMissing(step.key)])">{{ stepMissing(step.key) }}</span>
						</button>
					</li>
				</ol>
			</nav>

			<section v-if="activeStep.key !== 'review'" class="space-y-4 rounded-lg border border-gray-200 bg-white p-4" :aria-label="activeStep.label">
				<template v-for="field in stepFields(activeStep.key)" :key="field.fieldname">
					<AttachField
						v-if="isAttach(field)"
						:field="field"
						:value="form[field.fieldname]"
						:doctype="doctype"
						:docname="payload.name"
						:modified="payload.modified"
						:read-only="field.read_only"
						:required="isRequired(field)"
						:guidance="guidance[field.fieldname] || ''"
						:external-error="errors[field.fieldname]"
						@mounted="(el) => (fieldEls[field.fieldname] = el)"
						@uploading="(busy) => (uploadingCount += busy ? 1 : -1)"
						@updated="mergeServer"
					/>
					<FieldInput
						v-else
						:field="field"
						:model-value="form[field.fieldname]"
						:read-only="field.read_only"
						:required="isRequired(field)"
						:error="errors[field.fieldname]"
						@mounted="(el) => (fieldEls[field.fieldname] = el)"
						@update:model-value="(value) => setValue(field.fieldname, value)"
					/>
				</template>
				<p v-if="!stepFields(activeStep.key).length" class="text-sm text-gray-600">{{ __("Nothing to fill in this step.") }}</p>
			</section>

			<section v-else class="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
				<h2 class="text-base font-semibold">{{ __("Review") }}</h2>
				<template v-if="payload.editable">
					<p v-if="!missing.length" class="flex items-center gap-2 text-base text-green-800">
						<FeatherIcon name="check-circle" class="h-5 w-5" aria-hidden="true" />{{ __("Everything needed to complete this visit is filled in.") }}
					</p>
					<template v-else>
						<p class="text-base text-gray-800">{{ __("Fill these before completing:") }}</p>
						<ul class="space-y-1">
							<li v-for="field in missing" :key="field.fieldname">
								<button type="button" class="min-h-touch text-left text-base text-red-700 underline" @click="jumpTo(field.fieldname)">
									{{ field.label }} <span class="text-sm text-gray-600">({{ stepLabel(field.step) }})</span>
								</button>
							</li>
						</ul>
					</template>
				</template>
				<dl class="divide-y divide-gray-100">
					<div v-for="field in filledFields" :key="field.fieldname" class="flex justify-between gap-4 py-2">
						<dt class="text-sm text-gray-600">{{ field.label }}</dt>
						<dd class="text-right text-sm">{{ reviewValue(field) }}</dd>
					</div>
				</dl>
			</section>

			<div class="mt-4 flex gap-2">
				<Button v-if="current > 0" class="min-h-touch flex-1" @click="goTo(current - 1)">
					<template #prefix><FeatherIcon name="chevron-left" class="h-4 w-4" /></template>{{ __("Back") }}
				</Button>
				<Button v-if="current < allSteps.length - 1" class="min-h-touch flex-1" @click="goTo(current + 1)">
					{{ __("Next") }}<template #suffix><FeatherIcon name="chevron-right" class="h-4 w-4" /></template>
				</Button>
			</div>

			<StickyActions v-if="payload.editable" :error="formError">
				<SaveState class="flex-1" :state="saveState" />
				<Button class="min-h-touch" :loading="saving === 'save'" :disabled="busy || !dirty" @click="save('save')">{{ __("Save progress") }}</Button>
				<Button v-if="activeStep.key === 'review'" variant="solid" class="min-h-touch" :loading="saving === 'complete'" :disabled="busy" @click="complete">
					{{ __("Complete visit") }}
				</Button>
			</StickyActions>
		</template>
	</div>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue"
import { onBeforeRouteLeave } from "vue-router"
import { Button, FeatherIcon } from "frappe-ui"
import AttachField from "@/components/AttachField.vue"
import FieldInput from "@/components/FieldInput.vue"
import SaveState from "@/components/SaveState.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import StickyActions from "@/components/StickyActions.vue"
import { useDirtyTracking } from "@/composables/useDirty"
import { __ } from "@/plugins/translation"
import { session } from "@/data/session"
import { apiGet, apiPost, sessionUser as cookieUser } from "@/utils/api"
import { completionRequired, isEmptyValue, isVisible, missingForCompletion } from "@/utils/conditions"
import { formatDate } from "@/utils/format"
import { fromGeoJSON, mapsUrl } from "@/utils/geo"

const props = defineProps({
	doctype: { type: String, required: true },
	name: { type: String, required: true },
	// Mobile configuration that metadata cannot express.
	titleField: { type: String, required: true },
	guidance: { type: Object, default: () => ({}) },
	contextOnly: { type: Array, default: () => [] },
})
const API = "wahni_solar.field_portal.visits"
const ATTACH = ["Attach", "Attach Image"]

const payload = ref(null)
const loadError = ref("")
const form = reactive({})
const saved = ref({})
const errors = ref({})
const formError = ref("")
const conflict = ref("")
const saving = ref(null)
const saveFailed = ref(false)
const uploadingCount = ref(0)
const current = ref(0)
const fieldEls = reactive({})
const sessionUser = computed(() => session.info?.name || cookieUser())

const allSteps = computed(() => [...(payload.value?.steps || []), { key: "review", label: __("Review") }])
const activeStep = computed(() => allSteps.value[current.value] || allSteps.value[0])
const editableFields = computed(() => (payload.value?.fields || []).filter((f) => !f.read_only && f.supported && !ATTACH.includes(f.fieldtype)))
const dirty = computed(() => editableFields.value.some((f) => !same(form[f.fieldname], saved.value[f.fieldname])))
const busy = computed(() => !!saving.value || uploadingCount.value > 0)
const docValues = computed(() => ({ ...form, status: payload.value?.status }))
const missing = computed(() => missingForCompletion(payload.value?.fields || [], docValues.value))
const saveState = computed(() => {
	if (saving.value) return "saving"
	if (uploadingCount.value > 0) return "uploading"
	if (saveFailed.value) return "error"
	return dirty.value ? "dirty" : "saved"
})
useDirtyTracking(`${props.doctype}:${props.name}`, computed(() => dirty.value || uploadingCount.value > 0))

const ctx = computed(() => payload.value?.context || {})
const title = computed(() => form[props.titleField] || ctx.value.client_name || ctx.value.customer_name || ctx.value.customer || payload.value?.name)
const sourceLabel = computed(() => ctx.value.solar_proposal || ctx.value.project || "")
const subtitle = computed(() => [ctx.value.address, [ctx.value.location, ctx.value.place, ctx.value.landmark].filter(Boolean).join(", ")].filter(Boolean).join("\n"))
const phones = computed(() => [...new Set([ctx.value.contact_number, ctx.value.consumer_phone_number].filter(Boolean))])
const directions = computed(() => {
	const point = fromGeoJSON(form.geolocation || ctx.value.geolocation)
	if (point) return mapsUrl(point)
	const link = ctx.value.site_location_link
	if (link && /^https?:\/\//.test(link)) return link
	return mapsUrl({ address: [ctx.value.address, ctx.value.location || ctx.value.place, ctx.value.pincode].filter(Boolean).join(", ") })
})
const filledFields = computed(() => (payload.value?.fields || []).filter((f) => f.supported && !props.contextOnly.includes(f.fieldname) && !isEmptyValue(form[f.fieldname]) && !ATTACH.includes(f.fieldtype) && f.fieldtype !== "Geolocation"))

function same(a, b) {
	const norm = (v) => (v === undefined || v === "" ? null : typeof v === "number" ? v : v)
	return norm(a) === norm(b) || (norm(a) !== null && norm(b) !== null && String(norm(a)) === String(norm(b)))
}

function isAttach(field) {
	return ATTACH.includes(field.fieldtype)
}

function isRequired(field) {
	return completionRequired(field, docValues.value)
}

function stepFields(key) {
	return (payload.value?.fields || []).filter((field) => {
		if (field.step !== key || props.contextOnly.includes(field.fieldname)) return false
		// Required fields always show, so a missing value can be filled.
		if (completionRequired(field, docValues.value) && !field.read_only) return true
		if (field.read_only && isEmptyValue(form[field.fieldname])) return false
		return isVisible(field, docValues.value) || !isEmptyValue(form[field.fieldname])
	})
}

function stepMissing(key) {
	if (!payload.value?.editable) return 0
	if (key === "review") return 0
	return missing.value.filter((field) => field.step === key).length
}

function stepLabel(key) {
	return allSteps.value.find((s) => s.key === key)?.label || key
}

function reviewValue(field) {
	const value = form[field.fieldname]
	if (field.fieldtype === "Date") return formatDate(value)
	if (field.fieldtype === "Check") return value ? __("Yes") : __("No")
	return String(value)
}

function setValue(fieldname, value) {
	form[fieldname] = value
	if (errors.value[fieldname]) {
		const { [fieldname]: _removed, ...rest } = errors.value
		errors.value = rest
	}
}

function applyServer(data) {
	payload.value = data
	for (const key of Object.keys(form)) delete form[key]
	Object.assign(form, data.values)
	saved.value = { ...data.values }
}

// An attachment change saved on the server: keep unsaved local edits of other fields.
function mergeServer(data) {
	const local = Object.fromEntries(editableFields.value.filter((f) => !same(form[f.fieldname], saved.value[f.fieldname])).map((f) => [f.fieldname, form[f.fieldname]]))
	applyServer(data)
	Object.assign(form, local)
	saveFailed.value = false
}

async function load() {
	loadError.value = ""
	try {
		applyServer(await apiGet(`${API}.get_visit`, { doctype: props.doctype, name: props.name }))
	} catch (e) {
		loadError.value = e.message
	}
}

function changedValues() {
	return Object.fromEntries(editableFields.value.filter((f) => !same(form[f.fieldname], saved.value[f.fieldname])).map((f) => [f.fieldname, form[f.fieldname] ?? null]))
}

async function save(action) {
	if (saving.value) return // ignore duplicate taps
	saving.value = action
	formError.value = ""
	conflict.value = ""
	saveFailed.value = false
	try {
		applyServer(await apiPost(`${API}.save_visit`, {
			doctype: props.doctype, name: props.name, values: changedValues(), modified: payload.value.modified, action,
		}))
		errors.value = {}
		return true
	} catch (e) {
		saveFailed.value = true
		if (e.excType === "TimestampMismatchError") conflict.value = e.message
		else formError.value = e.message
		return false
	} finally {
		saving.value = null
	}
}

async function complete() {
	if (missing.value.length) {
		errors.value = Object.fromEntries(missing.value.map((f) => [f.fieldname, __("Required to complete the visit.")]))
		return jumpTo(missing.value[0].fieldname)
	}
	if (!window.confirm(__("Complete this visit? You will not be able to edit it afterwards."))) return
	await save("complete")
}

function goTo(index) {
	current.value = Math.max(0, Math.min(index, allSteps.value.length - 1))
	window.scrollTo({ top: 0 })
}

async function jumpTo(fieldname) {
	const field = payload.value.fields.find((f) => f.fieldname === fieldname)
	current.value = allSteps.value.findIndex((s) => s.key === field.step)
	await nextTick()
	const el = fieldEls[fieldname]
	el?.scrollIntoView?.({ block: "center" })
	el?.querySelector?.("input, select, textarea, button")?.focus()
}

async function reloadLatest() {
	conflict.value = ""
	saveFailed.value = false
	await load()
}

onBeforeRouteLeave(() => {
	if ((dirty.value || uploadingCount.value > 0) && !window.confirm(__("You have unsaved changes. Leave and discard them?"))) return false
	return true
})

watch(() => props.name, load, { immediate: true })
</script>
