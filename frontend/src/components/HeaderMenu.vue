<template>
	<div class="relative">
		<button
			ref="trigger"
			type="button"
			class="flex min-h-touch min-w-touch items-center justify-center rounded-full"
			:aria-label="__('Account menu')"
			:aria-expanded="open"
			aria-haspopup="menu"
			@click="open = !open"
		>
			<Avatar :label="info?.full_name || ''" :image="info?.user_image" size="lg" />
		</button>
		<div v-if="open" class="fixed inset-0 z-40" aria-hidden="true" @click="open = false" />
		<div
			v-if="open"
			role="menu"
			class="absolute right-1 top-12 z-50 w-64 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-lg"
			@keydown.escape="close"
		>
			<div class="border-b border-gray-100 px-4 py-3">
				<p class="truncate text-base font-medium">{{ info?.employee?.employee_name || info?.full_name }}</p>
				<p class="truncate text-sm text-gray-600">{{ info?.employee?.designation || info?.name }}</p>
			</div>
			<RouterLink role="menuitem" :to="{ name: 'Profile' }" class="menu-item" @click="open = false">
				<FeatherIcon name="user" class="h-5 w-5" aria-hidden="true" />{{ __("Profile") }}
			</RouterLink>
			<RouterLink v-if="!installed" role="menuitem" :to="{ name: 'Install' }" class="menu-item" @click="open = false">
				<FeatherIcon name="smartphone" class="h-5 w-5" aria-hidden="true" />{{ __("Install app") }}
			</RouterLink>
			<button role="menuitem" type="button" class="menu-item w-full text-red-700" @click="onLogout">
				<FeatherIcon name="log-out" class="h-5 w-5" aria-hidden="true" />{{ __("Log out") }}
			</button>
		</div>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { Avatar, FeatherIcon } from "frappe-ui"
import { __ } from "@/plugins/translation"
import { logout, session } from "@/data/session"
import { clearDirty, hasUnsavedChanges } from "@/composables/useDirty"
import { useInstall } from "@/composables/useInstall"

const open = ref(false)
const trigger = ref(null)
const info = computed(() => session.info)
const { installed } = useInstall()

function close() {
	open.value = false
	trigger.value?.focus()
}

function onLogout() {
	if (hasUnsavedChanges.value && !window.confirm(__("You have unsaved changes. Log out and discard them?"))) return
	clearDirty()
	open.value = false
	logout()
}
</script>

<style scoped>
.menu-item {
	@apply flex min-h-touch items-center gap-3 px-4 text-left text-base text-gray-800 hover:bg-gray-50;
}
</style>
