import { computed, reactive } from "vue"
import { prepareImage } from "@/utils/image"
import { uploadFile, validateFile } from "@/utils/upload"
import { __ } from "@/plugins/translation"

// Upload queue with progress, retry and cancel. `target()` returns {doctype, docname}
// (saving the record first when needed); `onUploaded(file, item)` binds the result.
export function useUploads({ target, onUploaded, imagesOnly = false }) {
	const pending = reactive([])
	const uploading = computed(() => pending.some((item) => !item.error))

	async function start(item) {
		item.error = ""
		item.progress = 0
		try {
			const { doctype, docname } = await target()
			const file = await prepareImage(item.file)
			const upload = uploadFile({ file, doctype, docname, fieldname: item.fieldname, onProgress: (p) => (item.progress = p) })
			item.abort = upload.abort
			const result = await upload.promise
			pending.splice(pending.indexOf(item), 1)
			await onUploaded(result, item)
		} catch (error) {
			if (pending.includes(item)) item.error = error.message || __("Upload failed.")
		}
	}

	function add(files, { fieldname = null } = {}) {
		const errors = []
		for (const file of files) {
			const problem = validateFile(file, { imagesOnly })
			if (problem) {
				errors.push(`${file.name}: ${__(problem)}`)
				continue
			}
			const item = reactive({ id: `${Date.now()}-${Math.random()}`, file, fieldname, progress: 0, error: "", abort: null })
			pending.push(item)
			start(item)
		}
		return errors
	}

	function cancel(item) {
		item.abort?.()
		const index = pending.indexOf(item)
		if (index >= 0) pending.splice(index, 1)
	}

	return { pending, uploading, add, retry: start, cancel }
}
