<template>
	<BottomSheet :model-value="connection.sessionExpired" :title="__('Session expired')" @update:model-value="(open) => (connection.sessionExpired = open)">
		<p class="mb-4 text-base text-gray-700">
			{{ __("Your session has ended. Anything not yet saved is still on this screen; log in again, then save.") }}
		</p>
		<LoginForm compact @success="onSuccess" />
	</BottomSheet>
</template>

<script setup>
import BottomSheet from "@/components/BottomSheet.vue"
import LoginForm from "@/components/LoginForm.vue"
import { __ } from "@/plugins/translation"
import { connection } from "@/utils/api"

function onSuccess() {
	connection.sessionExpired = false
}
</script>
