<template>
	<div>
		<ul v-if="files.length || pending.length" class="space-y-2">
			<li v-for="file in files" :key="file.name" class="flex items-center gap-3 rounded border border-gray-200 bg-white p-2">
				<a :href="file.file_url" target="_blank" rel="noopener" class="flex min-h-touch flex-1 items-center gap-3 overflow-hidden">
					<img v-if="isImage(file.file_url)" :src="file.file_url" alt="" class="h-12 w-12 shrink-0 rounded object-cover" loading="lazy" />
					<span v-else class="flex h-12 w-12 shrink-0 items-center justify-center rounded bg-gray-100">
						<FeatherIcon name="file-text" class="h-5 w-5 text-gray-600" aria-hidden="true" />
					</span>
					<span class="min-w-0">
						<span class="block truncate text-sm">{{ file.file_name }}</span>
						<span class="block text-xs text-gray-600">{{ fileSize(file.file_size) }}</span>
					</span>
				</a>
				<button
					v-if="editable"
					type="button"
					class="flex min-h-touch min-w-touch items-center justify-center text-red-700"
					:aria-label="__('Remove {0}', [file.file_name])"
					@click="$emit('remove', file)"
				>
					<FeatherIcon name="trash-2" class="h-5 w-5" aria-hidden="true" />
				</button>
			</li>
			<li v-for="item in pending" :key="item.id" class="rounded border border-gray-200 bg-white p-2">
				<div class="flex items-center gap-3">
					<FeatherIcon :name="item.error ? 'alert-triangle' : 'upload-cloud'" class="h-5 w-5 shrink-0" :class="item.error ? 'text-red-700' : 'text-gray-600'" aria-hidden="true" />
					<span class="min-w-0 flex-1 truncate text-sm">{{ item.file.name }}</span>
					<button v-if="item.error" type="button" class="min-h-touch px-2 text-sm underline" @click="$emit('retry', item)">{{ __("Retry") }}</button>
					<button type="button" class="min-h-touch px-2 text-sm text-gray-700 underline" @click="$emit('cancel', item)">
						{{ item.error ? __("Dismiss") : __("Cancel") }}
					</button>
				</div>
				<p v-if="item.error" class="mt-1 text-sm text-red-700" role="alert">{{ item.error }}</p>
				<div v-else class="mt-2 h-1.5 overflow-hidden rounded bg-gray-100" role="progressbar" :aria-valuenow="item.progress" aria-valuemin="0" aria-valuemax="100" :aria-label="__('Uploading {0}', [item.file.name])">
					<div class="h-full bg-brand-500 transition-all" :style="{ width: `${item.progress}%` }" />
				</div>
			</li>
		</ul>
		<p v-else class="text-sm text-gray-600">{{ emptyText }}</p>
	</div>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
import { __ } from "@/plugins/translation"
import { fileSize } from "@/utils/format"

defineProps({
	files: { type: Array, default: () => [] },
	pending: { type: Array, default: () => [] },
	editable: Boolean,
	emptyText: { type: String, default: "" },
})
defineEmits(["remove", "retry", "cancel"])

function isImage(url) {
	return /\.(png|jpe?g|gif|webp|heic|heif)$/i.test(url || "")
}
</script>
