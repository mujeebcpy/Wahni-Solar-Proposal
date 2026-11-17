<template>
	<div class="rounded-lg border p-3" :class="error ? 'border-red-500' : 'border-gray-200'" :ref="(el) => $emit('mounted', el)">
		<div class="mb-2 flex items-start justify-between gap-2">
			<div>
				<p class="text-base font-medium">
					{{ field.label }}
					<span v-if="required" class="text-red-600" aria-hidden="true">*</span>
				</p>
				<p class="text-xs" :class="required ? 'text-gray-800' : 'text-gray-600'">{{ required ? __("Required to complete") : __("Optional") }}</p>
				<p v-if="guidance" class="mt-1 text-sm text-gray-700">{{ guidance }}</p>
			</div>
			<FeatherIcon v-if="value" name="check-circle" class="h-5 w-5 shrink-0 text-green-700" :aria-label="__('Added')" />
		</div>

		<a v-if="value" :href="value" target="_blank" rel="noopener" class="block">
			<img v-if="isImage" :src="value" :alt="field.label" class="max-h-56 w-full rounded bg-gray-50 object-contain" loading="lazy" />
			<span v-else class="flex min-h-touch items-center gap-2 text-sm underline">
				<FeatherIcon name="file-text" class="h-4 w-4" aria-hidden="true" />{{ value.split("/").pop() }}
			</span>
		</a>
		<p v-else-if="readOnly" class="text-sm text-gray-600">{{ __("Not added") }}</p>

		<div v-if="uploading" class="mt-2" role="status">
			<p class="text-sm text-gray-700">{{ __("Uploading… {0}%", [progress]) }}</p>
			<div class="mt-1 h-1.5 overflow-hidden rounded bg-gray-100" role="progressbar" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100">
				<div class="h-full bg-brand-500" :style="{ width: `${progress}%` }" />
			</div>
			<button type="button" class="mt-1 min-h-touch text-sm underline" @click="cancel">{{ __("Cancel") }}</button>
		</div>
		<p v-if="error" class="mt-2 text-sm text-red-700" role="alert">
			{{ error }}
			<button v-if="lastFile" type="button" class="ml-2 underline" @click="upload(lastFile)">{{ __("Retry") }}</button>
		</p>

		<div v-if="!readOnly && !uploading" class="mt-3 grid grid-cols-2 gap-2">
			<label class="flex min-h-touch cursor-pointer items-center justify-center gap-2 rounded border border-gray-300 text-sm">
				<FeatherIcon name="camera" class="h-4 w-4" aria-hidden="true" />{{ value ? __("Retake") : __("Take photo") }}
				<input type="file" accept="image/*" capture="environment" class="sr-only" :aria-label="__('Take photo for {0}', [field.label])" @change="pick" />
			</label>
			<label class="flex min-h-touch cursor-pointer items-center justify-center gap-2 rounded border border-gray-300 text-sm">
				<FeatherIcon name="image" class="h-4 w-4" aria-hidden="true" />{{ value ? __("Replace") : __("Choose file") }}
				<input type="file" :accept="imagesOnly ? 'image/*' : ACCEPTED_FILES" class="sr-only" :aria-label="__('Choose file for {0}', [field.label])" @change="pick" />
			</label>
			<button v-if="value" type="button" class="col-span-2 min-h-touch text-sm text-red-700 underline" @click="remove">{{ __("Remove") }}</button>
		</div>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@/plugins/translation"
import { apiPost } from "@/utils/api"
import { prepareImage } from "@/utils/image"
import { ACCEPTED_FILES, uploadFile, validateFile } from "@/utils/upload"

const props = defineProps({
	field: { type: Object, required: true },
	value: { type: String, default: null },
	doctype: { type: String, required: true },
	docname: { type: String, required: true },
	modified: { type: String, required: true },
	readOnly: Boolean,
	required: Boolean,
	guidance: { type: String, default: "" },
	externalError: { type: String, default: "" },
})
const emit = defineEmits(["updated", "uploading", "mounted"])
const API = "wahni_solar.field_portal.visits"
const imagesOnly = computed(() => props.field.fieldtype === "Attach Image")
const isImage = computed(() => /\.(png|jpe?g|gif|webp)$/i.test(props.value || ""))
const uploading = ref(false)
const progress = ref(0)
const localError = ref("")
const lastFile = ref(null)
let abort = null
const error = computed(() => localError.value || props.externalError)

function pick(event) {
	const file = event.target.files?.[0]
	event.target.value = ""
	if (!file) return
	const problem = validateFile(file, { imagesOnly: imagesOnly.value })
	if (problem) {
		localError.value = __(problem)
		return
	}
	upload(file)
}

async function upload(file) {
	lastFile.value = file
	localError.value = ""
	uploading.value = true
	emit("uploading", true)
	progress.value = 0
	let uploaded = null
	try {
		const prepared = await prepareImage(file)
		const request = uploadFile({ file: prepared, doctype: props.doctype, docname: props.docname, onProgress: (p) => (progress.value = p) })
		abort = request.abort
		uploaded = await request.promise
		// Bind to the field; the server refuses if the visit changed elsewhere.
		emit("updated", await apiPost(`${API}.set_attachment`, {
			doctype: props.doctype, name: props.docname, fieldname: props.field.fieldname,
			file_url: uploaded.file_url, modified: props.modified,
		}))
		lastFile.value = null
	} catch (e) {
		localError.value = e.message
		if (uploaded) {
			// Do not leave an unbound upload behind.
			apiPost(`${API}.discard_upload`, { doctype: props.doctype, name: props.docname, file_name: uploaded.name }).catch(() => {})
		}
	} finally {
		uploading.value = false
		emit("uploading", false)
		abort = null
	}
}

function cancel() {
	abort?.()
}

async function remove() {
	if (!window.confirm(__("Remove {0}?", [props.field.label]))) return
	try {
		emit("updated", await apiPost(`${API}.clear_attachment`, {
			doctype: props.doctype, name: props.docname, fieldname: props.field.fieldname, modified: props.modified,
		}))
	} catch (e) {
		localError.value = e.message
	}
}
</script>
