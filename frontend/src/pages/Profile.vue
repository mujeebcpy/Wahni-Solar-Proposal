<template>
	<div class="space-y-4">
		<div class="flex items-center gap-4 rounded-lg border border-gray-200 bg-white p-4">
			<Avatar :label="info?.full_name || ''" :image="employee?.image || info?.user_image" size="3xl" />
			<div class="min-w-0">
				<p class="truncate text-lg font-semibold">{{ employee?.employee_name || info?.full_name }}</p>
				<p class="truncate text-sm text-gray-600">{{ info?.name }}</p>
			</div>
		</div>
		<dl class="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
			<div v-for="row in rows" :key="row.label" class="flex justify-between gap-4 px-4 py-3">
				<dt class="text-sm text-gray-600">{{ __(row.label) }}</dt>
				<dd class="text-right text-base">{{ row.value || "—" }}</dd>
			</div>
		</dl>
		<Button class="w-full min-h-touch" @click="onLogout">{{ __("Log out") }}</Button>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { Avatar, Button } from "frappe-ui"
import { __ } from "@/plugins/translation"
import { logout, session } from "@/data/session"
import { clearDirty, hasUnsavedChanges } from "@/composables/useDirty"

const info = computed(() => session.info)
const employee = computed(() => info.value?.employee)
const rows = computed(() => [
	{ label: "Employee ID", value: employee.value?.name },
	{ label: "Designation", value: employee.value?.designation },
	{ label: "Department", value: employee.value?.department },
	{ label: "Company", value: employee.value?.company },
	{ label: "Mobile", value: employee.value?.cell_number },
])

function onLogout() {
	if (hasUnsavedChanges.value && !window.confirm(__("You have unsaved changes. Log out and discard them?"))) return
	clearDirty()
	logout()
}
</script>
