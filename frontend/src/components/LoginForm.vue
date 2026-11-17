<template>
	<div>
		<form v-if="step === 'otp'" class="space-y-4" @submit.prevent="submitOtp" novalidate>
			<p class="text-base text-gray-700">{{ otpPrompt || __("Enter the verification code.") }}</p>
			<FormControl
				v-model="otp"
				:label="__('Verification code')"
				type="text"
				inputmode="numeric"
				autocomplete="one-time-code"
				placeholder="000000"
				required
			/>
			<ErrorMessage :message="error" />
			<Button type="submit" variant="solid" class="w-full min-h-touch" :loading="busy">{{ __("Verify") }}</Button>
			<button type="button" class="w-full min-h-touch text-sm text-gray-600 underline" @click="reset">
				{{ __("Use a different account") }}
			</button>
		</form>

		<template v-else>
			<form v-if="options.password_login" class="space-y-4" @submit.prevent="submitPassword" novalidate>
				<FormControl
					v-model="email"
					:label="__('Email or username')"
					type="text"
					autocomplete="username"
					autocapitalize="off"
					inputmode="email"
					required
				/>
				<FormControl
					v-model="password"
					:label="__('Password')"
					type="password"
					autocomplete="current-password"
					required
				/>
				<ErrorMessage :message="error" />
				<Button type="submit" variant="solid" class="w-full min-h-touch" :loading="busy">{{ __("Log in") }}</Button>
				<RouterLink v-if="!compact" :to="{ name: 'ForgotPassword' }" class="block py-2 text-center text-sm text-gray-600 underline">
					{{ __("Forgot password?") }}
				</RouterLink>
			</form>

			<div v-if="options.providers?.length" class="mt-4 space-y-3">
				<p v-if="options.password_login" class="text-center text-sm text-gray-500">{{ __("or") }}</p>
				<a
					v-for="provider in options.providers"
					:key="provider.name"
					:href="provider.auth_url"
					class="flex min-h-touch w-full items-center justify-center rounded border border-gray-300 bg-white px-4 text-base text-gray-800"
				>
					{{ __("Continue with {0}", [provider.label]) }}
				</a>
			</div>
			<p v-if="optionsLoaded && !options.password_login && !options.providers?.length" class="text-center text-base text-gray-600">
				{{ __("No login methods are available. Please contact your administrator.") }}
			</p>
		</template>

		<p v-if="step === 'password_reset'" class="mt-4 rounded bg-brand-50 p-3 text-sm text-gray-800" role="alert">
			{{ __("Your password has expired.") }}
			<a :href="resetLink" class="underline">{{ __("Set a new password") }}</a>
		</p>
	</div>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { Button, ErrorMessage, FormControl } from "frappe-ui"
import { __ } from "@/plugins/translation"
import { login, verifyOtp } from "@/data/session"
import { apiGet } from "@/utils/api"

defineProps({ compact: { type: Boolean, default: false } })
const emit = defineEmits(["success"])

const email = ref("")
const password = ref("")
const otp = ref("")
const tmpId = ref("")
const otpPrompt = ref("")
const resetLink = ref("")
const step = ref("password")
const error = ref("")
const busy = ref(false)
const options = ref({ password_login: true, providers: [] })
const optionsLoaded = ref(false)

onMounted(async () => {
	try {
		options.value = await apiGet("wahni_solar.field_portal.api.get_login_options")
	} catch {
		// Keep the password form available if the options request fails.
	} finally {
		optionsLoaded.value = true
	}
})

async function handle(result) {
	if (result.status === "ok") {
		password.value = ""
		otp.value = ""
		emit("success")
	} else if (result.status === "otp") {
		step.value = "otp"
		tmpId.value = result.tmpId
		otpPrompt.value = result.prompt
	} else if (result.status === "password_reset") {
		step.value = "password_reset"
		resetLink.value = result.link
	} else if (result.status === "standard_login") {
		// Verification setup this form cannot complete: use Frappe's own login page.
		window.location.assign(`/login?redirect-to=${encodeURIComponent(window.location.pathname)}`)
	} else {
		error.value = __("Login failed. Please try again.")
	}
}

async function submitPassword() {
	error.value = ""
	if (!email.value || !password.value) {
		error.value = __("Enter your email and password.")
		return
	}
	busy.value = true
	try {
		await handle(await login(email.value.trim(), password.value))
	} catch (e) {
		error.value = e.messages?.[0] || __("Invalid login. Please check your email and password.")
	} finally {
		busy.value = false
	}
}

async function submitOtp() {
	error.value = ""
	if (!otp.value) {
		error.value = __("Enter the verification code.")
		return
	}
	busy.value = true
	try {
		await handle(await verifyOtp(tmpId.value, otp.value.trim()))
	} catch (e) {
		error.value = e.network ? e.message : e.messages?.[0] || __("Invalid verification code.")
	} finally {
		busy.value = false
	}
}

function reset() {
	step.value = "password"
	otp.value = ""
	tmpId.value = ""
	error.value = ""
}
</script>
