// Frappe Geolocation fields store a GeoJSON FeatureCollection string.
export function toGeoJSON(lat, lng) {
	return JSON.stringify({
		type: "FeatureCollection",
		features: [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [Number(lng), Number(lat)] } }],
	})
}

export function fromGeoJSON(value) {
	if (!value) return null
	try {
		const data = typeof value === "string" ? JSON.parse(value) : value
		const point = data.features?.find((f) => f.geometry?.type === "Point")
		if (!point) return null
		const [lng, lat] = point.geometry.coordinates
		if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null
		return { lat, lng }
	} catch {
		return null
	}
}

export function validCoordinates(lat, lng) {
	const la = Number(lat)
	const ln = Number(lng)
	return lat !== "" && lng !== "" && Number.isFinite(la) && Number.isFinite(ln) && Math.abs(la) <= 90 && Math.abs(ln) <= 180
}

export function mapsUrl({ lat, lng, address } = {}) {
	if (Number.isFinite(lat) && Number.isFinite(lng)) return `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`
	if (address) return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`
	return null
}

export function safeHttpUrl(value) {
	try {
		const url = new URL(String(value))
		return ["http:", "https:"].includes(url.protocol) ? url.href : null
	} catch {
		return null
	}
}
