<template>
	<div class="flex min-h-[100dvh] flex-col items-center justify-center px-4 py-10 pt-safe-top pb-safe-bottom">
		<div class="w-full max-w-sm rounded-lg border border-gray-200 bg-white p-6 text-center shadow-sm">
			<div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-red-50">
				<FeatherIcon name="lock" class="h-6 w-6 text-red-700" aria-hidden="true" />
			</div>
			<h1 class="text-xl font-semibold">{{ loadFailed ? __("Could not load your account") : __("Access not available") }}</h1>
			<p class="mt-2 text-base text-gray-700">{{ reason }}</p>
			<p v-if="!loadFailed" class="mt-2 text-sm text-gray-600">
				{{ __("Ask the office to link your user to an active Employee with the Project Supervisor role.") }}
			</p>
			<div class="mt-6 space-y-3">
				<Button v-if="loadFailed" variant="solid" class="w-full min-h-touch" :loading="busy" @click="retry">{{ __("Try again") }}</Button>
				<Button class="w-full min-h-touch" @click="logout">{{ __("Log out") }}</Button>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { useRouter } from "vue-router"
import { Button, FeatherIcon } from "frappe-ui"
import { __ } from "@/plugins/translation"
import { loadSessionInfo, logout, session } from "@/data/session"

const router = useRouter()
const busy = ref(false)
const loadFailed = computed(() => !session.info)
const reason = computed(() =>
	session.info ? session.info.reason : session.infoError?.message || __("Please check your connection.")
)

async function retry() {
	busy.value = true
	try {
		await loadSessionInfo({ force: true })
		router.replace({ name: "Home" })
	} catch {
		// reason is shown from session.infoError
	} finally {
		busy.value = false
	}
}
</script>
