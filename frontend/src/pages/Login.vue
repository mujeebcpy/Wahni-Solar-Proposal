<template>
	<div class="flex min-h-[100dvh] flex-col items-center justify-center px-4 py-10 pt-safe-top pb-safe-bottom">
		<div class="w-full max-w-sm">
			<div class="mb-8 flex flex-col items-center gap-3">
				<BrandMark size="lg" />
				<h1 class="text-2xl font-semibold">{{ __("Wahni Field") }}</h1>
				<p class="text-center text-base text-gray-600">{{ __("Log in to record site visits, PMS visits and expenses.") }}</p>
			</div>
			<div class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
				<LoginForm @success="onSuccess" />
			</div>
		</div>
	</div>
</template>

<script setup>
import { useRoute, useRouter } from "vue-router"
import BrandMark from "@/components/BrandMark.vue"
import LoginForm from "@/components/LoginForm.vue"
import { safeRedirect } from "@/utils/redirect"

const route = useRoute()
const router = useRouter()

function onSuccess() {
	router.replace(safeRedirect(route.query.redirect) || { name: "Home" })
}
</script>
