<template>
	<img :src="logo" alt="" aria-hidden="true" :class="sizeClass" />
</template>

<script setup>
import { computed } from "vue"
const props = defineProps({ size: { type: String, default: "md" } })
const logo = "/assets/wahni_solar/images/wahni-solar-logo.svg"
const sizeClass = computed(() => ({ sm: "h-8 w-8", md: "h-10 w-10", lg: "h-16 w-16" })[props.size])
</script>
