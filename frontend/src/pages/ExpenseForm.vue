<template>
	<div class="pb-24">
		<p v-if="loadError" class="rounded bg-red-50 p-3 text-sm text-red-800" role="alert">
			{{ loadError }}
			<button type="button" class="ml-2 underline" @click="load">{{ __("Retry") }}</button>
		</p>
		<p v-else-if="loading" class="py-10 text-center text-sm text-gray-600" role="status">{{ __("Loading…") }}</p>

		<template v-else-if="options">
			<div v-if="conflict" class="mb-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm" role="alert">
				<p>{{ conflict }}</p>
				<button type="button" class="mt-2 min-h-touch font-medium underline" @click="reloadLatest">{{ __("Discard my edits and load the latest") }}</button>
			</div>

			<section v-if="doc" class="mb-4 flex flex-wrap items-center gap-2">
				<StatusBadge :label="doc.docstatus === 0 ? 'Draft' : doc.status" />
				<StatusBadge v-if="doc.approval_status !== 'Draft'" :label="doc.approval_status" />
				<span class="text-sm text-gray-600">{{ doc.name }}</span>
			</section>
			<p v-if="doc && doc.docstatus === 0 && doc.approval_status === 'Draft' && doc.expense_approver_name" class="mb-4 text-sm text-gray-700">
				{{ __("Waiting for approval by {0}.", [doc.expense_approver_name]) }}
			</p>

			<form novalidate @submit.prevent="save">
				<fieldset :disabled="!editable" class="space-y-4">
					<section class="space-y-4 rounded-lg border border-gray-200 bg-white p-4">
						<h2 class="text-base font-semibold">{{ __("Claim details") }}</h2>
						<div :ref="(el) => (fieldRefs.posting_date = el)">
							<FormControl v-model="form.posting_date" type="date" :label="__('Claim date')" required />
							<p v-if="errors.posting_date" class="mt-1 text-sm text-red-700">{{ __(errors.posting_date) }}</p>
						</div>
						<div :ref="(el) => (fieldRefs.expense_approver = el)">
							<label class="mb-1.5 block text-xs text-gray-600" for="approver">
								{{ __("Expense approver") }}<span v-if="options.approver_required" class="text-red-600" aria-hidden="true"> *</span>
							</label>
							<select id="approver" v-model="form.expense_approver" class="min-h-touch w-full rounded border bg-white px-3" :class="errors.expense_approver ? 'border-red-500' : 'border-gray-300'" :aria-invalid="!!errors.expense_approver">
								<option :value="null">{{ __("Select approver") }}</option>
								<option v-for="approver in approverOptions" :key="approver.value" :value="approver.value">{{ approver.label }}</option>
							</select>
							<p v-if="errors.expense_approver" class="mt-1 text-sm text-red-700">{{ __(errors.expense_approver) }}</p>
							<p v-else-if="!options.approvers.length" class="mt-1 text-sm text-amber-800">
								{{ __("No approver is set for you. Ask the office to set one on your Employee record.") }}
							</p>
						</div>
						<SearchSelect
							v-model="form.project"
							:label="__('Project (optional)')"
							:selected-label="form.project_label"
							:search="searchProjects"
							:disabled="!editable"
							@select="(option) => (form.project_label = option?.label || '')"
						/>
						<FormControl v-model="form.remark" type="textarea" :label="__('Notes (optional)')" />
					</section>

					<section class="rounded-lg border border-gray-200 bg-white p-4" :ref="(el) => (fieldRefs.expenses = el)">
						<div class="mb-3 flex items-center justify-between">
							<h2 class="text-base font-semibold">{{ __("Expenses") }}</h2>
							<span class="text-base font-semibold">{{ formatCurrency(localTotal, currency) }}</span>
						</div>
						<p v-if="errors.expenses" class="mb-2 text-sm text-red-700" role="alert">{{ __(errors.expenses) }}</p>
						<ul class="space-y-2">
							<li v-for="(item, index) in form.expenses" :key="item.key">
								<button
									type="button"
									class="flex min-h-touch w-full items-start gap-3 rounded border p-3 text-left"
									:class="itemErrors(index) ? 'border-red-500' : 'border-gray-200'"
									:disabled="!editable"
									@click="editItem(index)"
								>
									<span class="min-w-0 flex-1">
										<span class="block text-base font-medium">{{ item.expense_type || __("Choose expense type") }}</span>
										<span class="block text-sm text-gray-600">{{ formatDate(item.expense_date) }}<template v-if="item.description"> · {{ item.description }}</template></span>
										<span v-if="itemErrors(index)" class="block text-sm text-red-700">{{ __(itemErrors(index)) }}</span>
									</span>
									<span class="shrink-0 text-base">{{ formatCurrency(item.amount, currency) }}</span>
								</button>
							</li>
						</ul>
						<Button v-if="editable" class="mt-3 w-full min-h-touch" @click="addItem">
							<template #prefix><FeatherIcon name="plus" class="h-4 w-4" /></template>
							{{ __("Add expense") }}
						</Button>
					</section>
				</fieldset>

				<section class="mt-4 rounded-lg border border-gray-200 bg-white p-4">
					<h2 class="mb-3 text-base font-semibold">{{ __("Receipts") }}</h2>
					<AttachmentList
						:files="receipts"
						:pending="uploads.pending"
						:editable="editable"
						:empty-text="__('No receipts attached.')"
						@remove="removeReceipt"
						@retry="uploads.retry"
						@cancel="uploads.cancel"
					/>
					<p v-if="uploadErrors.length" class="mt-2 text-sm text-red-700" role="alert">{{ uploadErrors.join(" ") }}</p>
					<div v-if="editable" class="mt-3 grid grid-cols-2 gap-2">
						<label class="flex min-h-touch cursor-pointer items-center justify-center gap-2 rounded border border-gray-300 text-base">
							<FeatherIcon name="camera" class="h-4 w-4" aria-hidden="true" />{{ __("Take photo") }}
							<input type="file" accept="image/*" capture="environment" class="sr-only" @change="pickFiles" />
						</label>
						<label class="flex min-h-touch cursor-pointer items-center justify-center gap-2 rounded border border-gray-300 text-base">
							<FeatherIcon name="paperclip" class="h-4 w-4" aria-hidden="true" />{{ __("Choose file") }}
							<input type="file" :accept="ACCEPTED_FILES" multiple class="sr-only" @change="pickFiles" />
						</label>
					</div>
					<p v-if="editable && !doc" class="mt-2 text-xs text-gray-600">{{ __("Adding a receipt saves this claim as a draft first.") }}</p>
				</section>

				<section v-if="doc" class="mt-4 rounded-lg border border-gray-200 bg-white p-4">
					<h2 class="mb-2 text-base font-semibold">{{ __("Totals (from server)") }}</h2>
					<dl class="space-y-1 text-base">
						<div class="flex justify-between"><dt>{{ __("Claimed") }}</dt><dd>{{ formatCurrency(doc.total_claimed_amount, currency) }}</dd></div>
						<div v-if="doc.docstatus === 1" class="flex justify-between"><dt>{{ __("Sanctioned") }}</dt><dd>{{ formatCurrency(doc.total_sanctioned_amount, currency) }}</dd></div>
						<div v-for="tax in doc.taxes" :key="tax.description" class="flex justify-between"><dt>{{ tax.description }}</dt><dd>{{ formatCurrency(tax.tax_amount, currency) }}</dd></div>
						<div v-for="advance in doc.advances" :key="advance.employee_advance" class="flex justify-between"><dt>{{ __("Advance {0}", [advance.employee_advance]) }}</dt><dd>−{{ formatCurrency(advance.allocated_amount, currency) }}</dd></div>
						<div class="flex justify-between font-semibold"><dt>{{ __("Grand total") }}</dt><dd>{{ formatCurrency(doc.grand_total, currency) }}</dd></div>
						<div v-if="doc.total_amount_reimbursed" class="flex justify-between"><dt>{{ __("Reimbursed") }}</dt><dd>{{ formatCurrency(doc.total_amount_reimbursed, currency) }}</dd></div>
					</dl>
				</section>
			</form>

			<StickyActions v-if="editable" :error="errors.form ? __(errors.form) : ''">
				<SaveState class="flex-1" :state="saveState" />
				<Button
					v-for="action in doc?.actions || []"
					:key="action.action"
					class="min-h-touch"
					:disabled="dirty || busy"
					@click="runAction(action.action)"
				>
					{{ __(action.action) }}
				</Button>
				<Button variant="solid" class="min-h-touch px-5" :loading="saving" :disabled="busy || (!dirty && !!doc)" @click="save">
					{{ __("Save draft") }}
				</Button>
			</StickyActions>
		</template>

		<BottomSheet v-model="itemSheet" :title="editingIndex === null ? __('Add expense') : __('Edit expense')">
			<div class="space-y-4">
				<FormControl v-model="itemDraft.expense_date" type="date" :label="__('Date')" required />
				<div>
					<label for="expense-type" class="mb-1.5 block text-xs text-gray-600">{{ __("Expense type") }}<span class="text-red-600" aria-hidden="true"> *</span></label>
					<select id="expense-type" v-model="itemDraft.expense_type" class="min-h-touch w-full rounded border border-gray-300 bg-white px-3">
						<option :value="null">{{ __("Select type") }}</option>
						<option v-for="type in options?.expense_types || []" :key="type.name" :value="type.name">{{ type.name }}</option>
					</select>
				</div>
				<FormControl v-model="itemDraft.amount" type="number" inputmode="decimal" step="0.01" min="0" :label="__('Amount ({0})', [currency])" required />
				<FormControl v-model="itemDraft.description" type="textarea" :label="__('Description')" />
				<p v-if="itemError" class="text-sm text-red-700" role="alert">{{ itemError }}</p>
			</div>
			<template #footer>
				<div class="flex gap-2">
					<Button v-if="editingIndex !== null" class="min-h-touch" theme="red" @click="deleteItem">{{ __("Remove") }}</Button>
					<Button variant="solid" class="min-h-touch flex-1" @click="commitItem">{{ __("Done") }}</Button>
				</div>
			</template>
		</BottomSheet>
	</div>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue"
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router"
import { Button, FeatherIcon, FormControl } from "frappe-ui"
import AttachmentList from "@/components/AttachmentList.vue"
import BottomSheet from "@/components/BottomSheet.vue"
import SaveState from "@/components/SaveState.vue"
import SearchSelect from "@/components/SearchSelect.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import StickyActions from "@/components/StickyActions.vue"
import { useDirtyTracking } from "@/composables/useDirty"
import { useUploads } from "@/composables/useUploads"
import { __ } from "@/plugins/translation"
import { apiGet, apiPost, stripHtml } from "@/utils/api"
import { formatCurrency, formatDate, newToken, today } from "@/utils/format"
import { ACCEPTED_FILES } from "@/utils/upload"
import { validateClaim } from "@/utils/expense"

const API = "wahni_solar.field_portal.expenses"
const route = useRoute()
const router = useRouter()

const options = ref(null)
const doc = ref(null)
const loading = ref(true)
const loadError = ref("")
const saving = ref(false)
const actionBusy = ref(false)
const saveFailed = ref(false)
const conflict = ref("")
const errors = ref({})
const fieldRefs = reactive({})
const receipts = ref([])
const uploadErrors = ref([])
const clientToken = newToken()
const form = reactive(blankForm())
const snapshot = ref(serialize())

const currency = computed(() => doc.value?.currency || options.value?.currency || "INR")
const editable = computed(() => (doc.value ? doc.value.editable : true))
const dirty = computed(() => serialize() !== snapshot.value)
const busy = computed(() => saving.value || actionBusy.value)
const localTotal = computed(() => form.expenses.reduce((sum, item) => sum + Number(item.amount || 0), 0))
const approverOptions = computed(() => {
	const list = [...(options.value?.approvers || [])]
	if (form.expense_approver && !list.some((a) => a.value === form.expense_approver)) {
		list.push({ value: form.expense_approver, label: doc.value?.expense_approver_name || form.expense_approver })
	}
	return list
})

const uploads = reactive(
	useUploads({
		target: async () => {
			if (!doc.value) await save()
			if (!doc.value) throw new Error(__("Save the claim before adding receipts."))
			return { doctype: "Expense Claim", docname: doc.value.name }
		},
		onUploaded: (file) => {
			receipts.value = [...receipts.value, file]
		},
	})
)
const saveState = computed(() => {
	if (saving.value) return "saving"
	if (uploads.uploading) return "uploading"
	if (saveFailed.value) return "error"
	if (!doc.value) return "new"
	return dirty.value ? "dirty" : "saved"
})
useDirtyTracking(`expense:${clientToken}`, computed(() => dirty.value || uploads.uploading))

function blankForm() {
	return { posting_date: today(), expense_approver: null, project: null, project_label: "", remark: "", expenses: [] }
}

function serialize() {
	const { project_label, ...rest } = form
	return JSON.stringify({ ...rest, expenses: rest.expenses.map(({ key, ...item }) => item) })
}

function fromDoc(data) {
	doc.value = data
	receipts.value = data.receipts || []
	Object.assign(form, {
		posting_date: data.posting_date,
		expense_approver: data.expense_approver || null,
		project: data.project || null,
		project_label: data.project || "",
		remark: data.remark || "",
		expenses: data.expenses.map((item) => ({
			key: item.name,
			expense_date: item.expense_date,
			expense_type: item.expense_type,
			description: stripHtml(item.description || ""),
			amount: item.amount,
			project: item.project || null,
		})),
	})
	snapshot.value = serialize()
}

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		options.value = await apiGet(`${API}.get_form_options`)
		if (route.params.name && route.params.name !== "new") {
			fromDoc(await apiGet(`${API}.get_claim`, { name: route.params.name }))
		} else {
			Object.assign(form, blankForm(), { expense_approver: options.value.approvers[0]?.value || null })
			snapshot.value = serialize()
			form.expenses.length || openNewItem()
		}
	} catch (e) {
		loadError.value = e.message
	} finally {
		loading.value = false
	}
}

async function focusFirstError() {
	await nextTick()
	const key = Object.keys(errors.value)[0]
	if (!key) return
	const el = fieldRefs[key.startsWith("expenses") ? "expenses" : key]
	el?.scrollIntoView?.({ behavior: "smooth", block: "center" })
	el?.querySelector?.("input, select, textarea, button")?.focus()
}

async function save() {
	if (saving.value) return // no duplicate taps
	errors.value = validateClaim(form, { approverRequired: !!options.value.approver_required })
	if (Object.keys(errors.value).length) {
		focusFirstError()
		return
	}
	saving.value = true
	saveFailed.value = false
	conflict.value = ""
	try {
		const values = {
			name: doc.value?.name,
			modified: doc.value?.modified,
			posting_date: form.posting_date,
			expense_approver: form.expense_approver,
			project: form.project,
			remark: form.remark,
			expenses: form.expenses.map(({ key, ...item }) => item),
		}
		const result = await apiPost(`${API}.save_claim`, { values, client_token: doc.value ? null : clientToken })
		const label = form.project_label
		fromDoc({ ...result, receipts: result.receipts })
		form.project_label = label
		snapshot.value = serialize()
		if (route.params.name !== result.name) router.replace({ name: "Expense", params: { name: result.name } })
	} catch (e) {
		saveFailed.value = true
		if (e.excType === "TimestampMismatchError") conflict.value = e.message
		else errors.value = { form: e.message }
	} finally {
		saving.value = false
	}
}

async function reloadLatest() {
	conflict.value = ""
	saveFailed.value = false
	fromDoc(await apiGet(`${API}.get_claim`, { name: doc.value.name }))
}

async function runAction(action) {
	if (!window.confirm(__("{0} this claim?", [__(action)]))) return
	actionBusy.value = true
	try {
		fromDoc(await apiPost(`${API}.apply_action`, { name: doc.value.name, action, modified: doc.value.modified }))
	} catch (e) {
		window.alert(e.message)
	} finally {
		actionBusy.value = false
	}
}

async function removeReceipt(file) {
	if (!window.confirm(__("Remove {0}?", [file.file_name]))) return
	try {
		const result = await apiPost(`${API}.remove_receipt`, { name: doc.value.name, file_name: file.name })
		receipts.value = result.receipts
	} catch (e) {
		window.alert(e.message)
	}
}

function pickFiles(event) {
	uploadErrors.value = uploads.add([...event.target.files])
	event.target.value = ""
}

// Expense item sheet
const itemSheet = ref(false)
const editingIndex = ref(null)
const itemDraft = reactive({})
const itemError = ref("")

function openNewItem() {
	editingIndex.value = null
	Object.assign(itemDraft, { expense_date: form.posting_date || today(), expense_type: options.value?.expense_types.length === 1 ? options.value.expense_types[0].name : null, amount: null, description: "", project: null })
	itemError.value = ""
	itemSheet.value = true
}
const addItem = openNewItem

function editItem(index) {
	editingIndex.value = index
	Object.assign(itemDraft, { ...form.expenses[index] })
	itemError.value = ""
	itemSheet.value = true
}

function commitItem() {
	if (!itemDraft.expense_type) return (itemError.value = __("Choose an expense type."))
	if (!(Number(itemDraft.amount) > 0)) return (itemError.value = __("Enter an amount greater than zero."))
	if (!itemDraft.expense_date) return (itemError.value = __("Choose a date."))
	const item = { key: itemDraft.key || newToken(), expense_date: itemDraft.expense_date, expense_type: itemDraft.expense_type, description: itemDraft.description || "", amount: Number(itemDraft.amount), project: itemDraft.project || null }
	if (editingIndex.value === null) form.expenses.push(item)
	else form.expenses.splice(editingIndex.value, 1, item)
	delete errors.value.expenses
	itemSheet.value = false
}

function deleteItem() {
	form.expenses.splice(editingIndex.value, 1)
	itemSheet.value = false
}

function itemErrors(index) {
	return errors.value[`expenses.${index}`]
}

async function searchProjects(txt, start, pageLength) {
	const rows = await apiGet(`${API}.search_projects`, { txt, start, page_length: pageLength })
	return rows.map((p) => ({ value: p.name, label: p.project_name || p.name, description: p.customer || p.name }))
}

onBeforeRouteLeave(() => {
	if ((dirty.value || uploads.uploading) && !window.confirm(__("You have unsaved changes. Leave and discard them?"))) return false
	return true
})

watch(
	() => route.params.name,
	(name, previous) => {
		// Our own replace after the first save keeps this instance and its state.
		if (name && previous && doc.value?.name === name) return
		if (name) load()
	},
	{ immediate: true }
)
</script>
