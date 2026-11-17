// Phone photos are large; shrink them while keeping ratings/receipts readable.
export const MAX_DIMENSION = 2400
export const JPEG_QUALITY = 0.85
const COMPRESS_ABOVE = 1.5 * 1024 * 1024

export function targetSize(width, height, max = MAX_DIMENSION) {
	const scale = Math.min(1, max / Math.max(width, height))
	return { width: Math.round(width * scale), height: Math.round(height * scale) }
}

export async function prepareImage(file) {
	if (!file.type.startsWith("image/") || file.type === "image/gif" || file.type === "image/svg+xml") return file
	if (file.size <= COMPRESS_ABOVE) return file
	try {
		// imageOrientation applies EXIF rotation so photos are not sideways.
		const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" })
		const { width, height } = targetSize(bitmap.width, bitmap.height)
		const canvas = document.createElement("canvas")
		canvas.width = width
		canvas.height = height
		canvas.getContext("2d").drawImage(bitmap, 0, 0, width, height)
		bitmap.close?.()
		const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY))
		if (!blob || blob.size >= file.size) return file
		const name = file.name.replace(/\.[^.]+$/, "") + ".jpg"
		return new File([blob], name, { type: "image/jpeg", lastModified: Date.now() })
	} catch {
		// HEIC or other formats the browser cannot decode: upload the original.
		return file
	}
}
