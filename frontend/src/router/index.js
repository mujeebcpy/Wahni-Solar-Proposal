import { createRouter, createWebHistory } from "vue-router"
import { decideNavigation } from "./guard"
import { isLoggedIn, loadSessionInfo } from "@/data/session"

const AppShell = () => import("@/components/AppShell.vue")

export const routes = [
	{ path: "/login", name: "Login", component: () => import("@/pages/Login.vue") },
	{ path: "/forgot-password", name: "ForgotPassword", component: () => import("@/pages/ForgotPassword.vue") },
	{ path: "/access-denied", name: "AccessDenied", component: () => import("@/pages/AccessDenied.vue") },
	{
		path: "/",
		component: AppShell,
		children: [
			{ path: "", name: "Home", component: () => import("@/pages/Home.vue"), meta: { tab: "home" } },
			{ path: "profile", name: "Profile", component: () => import("@/pages/Profile.vue"), meta: { title: "Profile" } },
			{ path: "install", name: "Install", component: () => import("@/pages/InstallHelp.vue"), meta: { title: "Install app" } },
			{ path: "site-visits", name: "SiteVisits", component: () => import("@/pages/VisitList.vue"), meta: { tab: "site-visits", title: "Site Visits", doctype: "Site Visit" } },
			// "/site-visits/new" and "/site-visits/:name" share one record (name === "new").
			{ path: "site-visits/:name", name: "SiteVisit", component: () => import("@/pages/VisitPage.vue"), meta: { tab: "site-visits", title: "Site Visit", doctype: "Site Visit", hideNav: true } },
			{ path: "pms-visits", name: "PMSVisits", component: () => import("@/pages/VisitList.vue"), meta: { tab: "pms", title: "PMS Visits", doctype: "PMS Visit" } },
			{ path: "pms-visits/:name", name: "PMSVisit", component: () => import("@/pages/VisitPage.vue"), meta: { tab: "pms", title: "PMS Visit", doctype: "PMS Visit", hideNav: true } },
			{ path: "expenses", name: "Expenses", component: () => import("@/pages/ExpenseList.vue"), meta: { tab: "expenses", title: "Expenses" } },
			// One record for /expenses/new and /expenses/:name so the first save keeps the form instance.
			{ path: "expenses/:name", name: "Expense", component: () => import("@/pages/ExpenseForm.vue"), meta: { tab: "expenses", title: "Expense Claim", hideNav: true } },
			{ path: ":pathMatch(.*)*", name: "NotFound", component: () => import("@/pages/NotFound.vue"), meta: { title: "Not found" } },
		],
	},
]

const router = createRouter({
	history: createWebHistory("/field"),
	routes,
	scrollBehavior: (to, from, saved) => saved || { top: 0 },
})

router.beforeEach(async (to) => {
	let info = null
	if (isLoggedIn()) {
		try {
			info = await loadSessionInfo()
		} catch {
			info = null
		}
	}
	return decideNavigation(to, { loggedIn: isLoggedIn(), info }) ?? true
})

router.afterEach((to) => {
	const title = to.meta?.title
	document.title = title ? `${title} · Wahni Field` : "Wahni Field"
})

export default router
