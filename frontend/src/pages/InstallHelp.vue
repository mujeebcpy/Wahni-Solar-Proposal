<template>
	<div class="space-y-4">
		<div v-if="installed" class="rounded-lg border border-green-200 bg-green-50 p-4 text-base" role="status">
			{{ __("Wahni Field is installed on this device.") }}
		</div>
		<template v-else>
			<div v-if="canPrompt" class="rounded-lg border border-gray-200 bg-white p-4">
				<p class="text-base">{{ __("Install Wahni Field on this device for quick, full-screen access.") }}</p>
				<Button variant="solid" class="mt-3 w-full min-h-touch" @click="promptInstall">{{ __("Install app") }}</Button>
			</div>
			<section class="rounded-lg border border-gray-200 bg-white p-4" :class="{ 'ring-2 ring-brand-500': ios }">
				<h2 class="text-base font-semibold">{{ __("iPhone or iPad (Safari)") }}</h2>
				<ol class="mt-2 list-decimal space-y-1 pl-5 text-base text-gray-800">
					<li>{{ __("Open this page in Safari.") }}</li>
					<li>{{ __("Tap the Share button.") }}</li>
					<li>{{ __("Choose \"Add to Home Screen\", then tap Add.") }}</li>
				</ol>
			</section>
			<section class="rounded-lg border border-gray-200 bg-white p-4" :class="{ 'ring-2 ring-brand-500': !ios }">
				<h2 class="text-base font-semibold">{{ __("Android (Chrome)") }}</h2>
				<ol class="mt-2 list-decimal space-y-1 pl-5 text-base text-gray-800">
					<li>{{ __("Open the Chrome menu (⋮).") }}</li>
					<li>{{ __("Tap \"Install app\" or \"Add to Home screen\".") }}</li>
				</ol>
			</section>
			<p class="text-sm text-gray-600">
				{{ __("The installed app still needs an internet connection to load and save your work.") }}
			</p>
		</template>
	</div>
</template>

<script setup>
import { Button } from "frappe-ui"
import { __ } from "@/plugins/translation"
import { useInstall } from "@/composables/useInstall"

const { canPrompt, installed, ios, promptInstall } = useInstall()
</script>
