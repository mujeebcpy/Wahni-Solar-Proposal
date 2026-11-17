<template>
	<div class="flex min-h-[100dvh] flex-col items-center justify-center px-4 py-10 pt-safe-top pb-safe-bottom">
		<div class="w-full max-w-sm">
			<div class="mb-6 flex flex-col items-center gap-3">
				<BrandMark size="lg" />
				<h1 class="text-2xl font-semibold">{{ __("Reset password") }}</h1>
			</div>
			<div class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
				<p v-if="sent" role="status" class="text-base text-gray-800">
					{{ __("If an account exists for {0}, password reset instructions have been emailed.", [email]) }}
				</p>
				<form v-else class="space-y-4" @submit.prevent="submit" novalidate>
					<FormControl v-model="email" :label="__('Email')" type="email" autocomplete="email" inputmode="email" required />
					<ErrorMessage :message="error" />
					<Button type="submit" variant="solid" class="w-full min-h-touch" :loading="busy">{{ __("Send reset link") }}</Button>
				</form>
				<RouterLink :to="{ name: 'Login' }" class="mt-4 block py-2 text-center text-sm text-gray-600 underline">
					{{ __("Back to login") }}
				</RouterLink>
			</div>
		</div>
	</div>
</template>

<script setup>
import { ref } from "vue"
import { Button, ErrorMessage, FormControl } from "frappe-ui"
import BrandMark from "@/components/BrandMark.vue"
import { __ } from "@/plugins/translation"
import { apiPost } from "@/utils/api"

const email = ref("")
const error = ref("")
const busy = ref(false)
const sent = ref(false)

async function submit() {
	error.value = ""
	if (!/.+@.+\..+/.test(email.value)) {
		error.value = __("Enter a valid email address.")
		return
	}
	busy.value = true
	try {
		await apiPost("frappe.core.doctype.user.user.reset_password", { user: email.value.trim() })
		sent.value = true
	} catch (e) {
		// Do not reveal whether the account exists; only surface transport problems.
		if (e.network) error.value = e.message
		else sent.value = true
	} finally {
		busy.value = false
	}
}
</script>
