<template>
	<component :is="newPage" v-if="route.params.name === 'new'" />
	<VisitForm
		v-else
		:key="`${doctype}:${route.params.name}`"
		:doctype="doctype"
		:name="route.params.name"
		:title-field="config.titleField"
		:context-only="config.contextOnly"
		:guidance="guidanceText"
	/>
</template>

<script setup>
import { computed, defineAsyncComponent } from "vue"
import { useRoute } from "vue-router"
import VisitForm from "@/components/VisitForm.vue"
import { __ } from "@/plugins/translation"
import { VISIT_TYPES } from "@/utils/visitTypes"

const route = useRoute()
const doctype = computed(() => route.meta.doctype)
const config = computed(() => VISIT_TYPES[doctype.value])
const guidanceText = computed(() => Object.fromEntries(Object.entries(config.value.guidance).map(([k, v]) => [k, __(v)])))
const newPage = computed(() =>
	doctype.value === "Site Visit"
		? defineAsyncComponent(() => import("@/pages/SiteVisitNew.vue"))
		: defineAsyncComponent(() => import("@/pages/PMSVisitNew.vue"))
)
</script>
