<template>
	<div>
		<p v-if="point" class="mb-2 text-sm text-gray-800">
			{{ point.lat.toFixed(6) }}, {{ point.lng.toFixed(6) }}
			<a :href="mapsUrl(point)" target="_blank" rel="noopener" class="ml-2 underline">{{ __("Open map") }}</a>
		</p>
		<p v-else class="mb-2 text-sm text-gray-600">{{ __("No location recorded.") }}</p>
		<template v-if="!readOnly">
			<div class="grid grid-cols-2 gap-2">
				<Button class="min-h-touch" :loading="locating" @click="capture">
					<template #prefix><FeatherIcon name="crosshair" class="h-4 w-4" /></template>
					{{ __("Use my location") }}
				</Button>
				<Button class="min-h-touch" @click="manual = !manual">{{ __("Enter manually") }}</Button>
			</div>
			<p v-if="message" class="mt-2 text-sm" :class="failed ? 'text-red-700' : 'text-gray-700'" role="status">{{ message }}</p>
			<div v-if="manual" class="mt-3 grid grid-cols-2 gap-2">
				<FormControl v-model="lat" type="number" inputmode="decimal" step="any" :label="__('Latitude')" />
				<FormControl v-model="lng" type="number" inputmode="decimal" step="any" :label="__('Longitude')" />
				<Button class="col-span-2 min-h-touch" @click="applyManual">{{ __("Set location") }}</Button>
			</div>
			<button v-if="point" type="button" class="mt-2 min-h-touch text-sm text-red-700 underline" @click="$emit('update:modelValue', null)">
				{{ __("Clear location") }}
			</button>
		</template>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { Button, FeatherIcon, FormControl } from "frappe-ui"
import { __ } from "@/plugins/translation"
import { fromGeoJSON, isSecureOrigin, locationPermissionState, mapsUrl, toGeoJSON, validCoordinates } from "@/utils/geo"

const props = defineProps({ modelValue: { type: String, default: null }, readOnly: Boolean })
const emit = defineEmits(["update:modelValue"])
const point = computed(() => fromGeoJSON(props.modelValue))
const locating = ref(false)
const manual = ref(false)
const message = ref("")
const failed = ref(false)
const lat = ref(point.value?.lat ?? "")
const lng = ref(point.value?.lng ?? "")

// Location is read once, only when the user asks; never tracked continuously.
function fail(text) {
	locating.value = false
	failed.value = true
	manual.value = true
	message.value = text
}

async function capture() {
	message.value = ""
	failed.value = false
	if (!isSecureOrigin()) {
		fail(__("Location needs a secure (https://) connection. Open Wahni Field over https, or enter the coordinates manually."))
		return
	}
	if (!navigator.geolocation) {
		fail(__("Location is not available on this device. Enter it manually."))
		return
	}
	locating.value = true
	// A previously blocked site never shows the prompt again: tell the user how to unblock it.
	if ((await locationPermissionState()) === "denied") {
		fail(__("Location is blocked for this site. Allow it in the browser's site settings (lock icon next to the address), then try again."))
		return
	}
	navigator.geolocation.getCurrentPosition(
		(position) => {
			locating.value = false
			const { latitude, longitude, accuracy } = position.coords
			emit("update:modelValue", toGeoJSON(latitude, longitude))
			message.value = __("Location captured (accuracy about {0} m).", [Math.round(accuracy)])
		},
		(error) =>
			fail(
				error.code === 1
					? __("Location permission was denied. Allow location for this site (and turn on device location), or enter the coordinates manually.")
					: error.code === 3
						? __("Getting your location took too long. Move to open sky and try again, or enter it manually.")
						: __("Could not get your location. Check that device location is on, then try again or enter it manually.")
			),
		{ enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
	)
}

function applyManual() {
	if (!validCoordinates(lat.value, lng.value)) {
		failed.value = true
		message.value = __("Enter a valid latitude (−90 to 90) and longitude (−180 to 180).")
		return
	}
	failed.value = false
	message.value = ""
	emit("update:modelValue", toGeoJSON(lat.value, lng.value))
	manual.value = false
}
</script>
