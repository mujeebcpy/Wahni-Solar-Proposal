<template>
	<Teleport to="body">
		<div v-if="modelValue" class="fixed inset-0 z-50 flex items-end justify-center sm:items-center" @keydown.escape="close">
			<div class="absolute inset-0 bg-black/40" aria-hidden="true" @click="close" />
			<div
				ref="panel"
				role="dialog"
				aria-modal="true"
				:aria-labelledby="titleId"
				tabindex="-1"
				class="relative flex max-h-[92dvh] w-full flex-col rounded-t-2xl bg-white pb-safe-bottom shadow-xl outline-none sm:max-w-lg sm:rounded-2xl"
			>
				<div class="flex items-center gap-2 border-b border-gray-100 px-4 py-2">
					<h2 :id="titleId" class="flex-1 text-lg font-semibold">{{ title }}</h2>
					<button type="button" class="flex min-h-touch min-w-touch items-center justify-center" :aria-label="__('Close')" @click="close">
						<FeatherIcon name="x" class="h-5 w-5" aria-hidden="true" />
					</button>
				</div>
				<div class="flex-1 overflow-y-auto px-4 py-3"><slot /></div>
				<div v-if="$slots.footer" class="border-t border-gray-100 px-4 py-3"><slot name="footer" /></div>
			</div>
		</div>
	</Teleport>
</template>

<script setup>
import { nextTick, ref, watch } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@/plugins/translation"

const props = defineProps({ modelValue: Boolean, title: { type: String, default: "" } })
const emit = defineEmits(["update:modelValue"])
const panel = ref(null)
const titleId = `sheet-${Math.random().toString(36).slice(2)}`
let returnFocus = null

watch(
	() => props.modelValue,
	async (open) => {
		if (open) {
			returnFocus = document.activeElement
			await nextTick()
			const first = panel.value?.querySelector("input, select, textarea, button:not([aria-label='Close'])")
			;(first || panel.value)?.focus()
		} else {
			returnFocus?.focus?.()
		}
	}
)

function close() {
	emit("update:modelValue", false)
}
</script>
