import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import { VitePWA } from "vite-plugin-pwa"
import path from "path"
import fs from "fs"

const ASSET_BASE = "/assets/wahni_solar/field/"
const FIELD_SCOPE = "/field/"

export default defineConfig(({ command }) => ({
	// Assets are served by Frappe from /assets; the router history lives at /field/.
	base: command === "build" ? ASSET_BASE : "/",
	server: { port: 8081, proxy: proxyOptions(), allowedHosts: true },
	plugins: [
		vue(),
		VitePWA({
			strategies: "generateSW",
			registerType: "prompt",
			injectRegister: null,
			filename: "sw.js",
			scope: FIELD_SCOPE,
			manifestFilename: "manifest.webmanifest",
			includeManifestIcons: true,
			devOptions: { enabled: false },
			integration: {
				// The plugin adds the web manifest/icons as relative entries, which would
				// resolve against /field/sw.js and cache SPA HTML. Make them absolute.
				beforeBuildServiceWorker(options) {
					options.workbox.additionalManifestEntries = (options.workbox.additionalManifestEntries || []).map(
						(entry) => {
							const url = typeof entry === "string" ? entry : entry.url
							const absolute = url.startsWith("/") ? url : ASSET_BASE + url
							return typeof entry === "string" ? absolute : { ...entry, url: absolute }
						}
					)
				},
			},
			manifest: {
				id: FIELD_SCOPE,
				name: "Wahni Field",
				short_name: "Wahni Field",
				description: "Site visits, PMS visits and expense claims for Wahni field staff",
				start_url: FIELD_SCOPE,
				scope: FIELD_SCOPE,
				display: "standalone",
				orientation: "portrait",
				background_color: "#ffffff",
				theme_color: "#f59e0b",
				icons: [
					{ src: `${ASSET_BASE}icons/icon-192.png`, sizes: "192x192", type: "image/png", purpose: "any" },
					{ src: `${ASSET_BASE}icons/icon-512.png`, sizes: "512x512", type: "image/png", purpose: "any" },
					{ src: `${ASSET_BASE}icons/maskable-512.png`, sizes: "512x512", type: "image/png", purpose: "maskable" },
				],
			},
			workbox: {
				// Versioned static assets only: never HTML, API responses or private files.
				globPatterns: ["**/*.{js,css,woff2,svg,png}"],
				globIgnores: ["**/index.html"],
				navigateFallback: null,
				runtimeCaching: [],
				cacheId: "wahni-field",
				cleanupOutdatedCaches: true,
				// The worker is served from /field/sw.js: make precache URLs absolute.
				modifyURLPrefix: { "": ASSET_BASE },
				inlineWorkboxRuntime: true,
				skipWaiting: false,
				clientsClaim: false,
				sourcemap: false,
			},
		}),
	],
	resolve: { alias: { "@": path.resolve(__dirname, "src") } },
	build: {
		outDir: "../wahni_solar/public/field",
		emptyOutDir: true,
		target: "es2018",
		commonjsOptions: { include: [/tailwind.config.js/, /node_modules/] },
		rollupOptions: { output: { manualChunks: { "frappe-ui": ["frappe-ui"] } } },
	},
	optimizeDeps: { include: ["frappe-ui > feather-icons", "showdown", "engine.io-client"] },
	test: { environment: "jsdom", include: ["tests/**/*.test.js"] },
}))

function proxyOptions() {
	const config = commonSiteConfig()
	const port = config?.webserver_port || 8000
	return {
		"^/(app|desk|login|api|assets|files|private|field/sw.js)": {
			target: `http://127.0.0.1:${port}`,
			ws: true,
			router: (req) => `http://${req.headers.host.split(":")[0]}:${port}`,
		},
	}
}

function commonSiteConfig() {
	let dir = path.resolve(".")
	while (dir !== "/") {
		const file = path.join(dir, "sites", "common_site_config.json")
		if (fs.existsSync(file)) return JSON.parse(fs.readFileSync(file))
		dir = path.resolve(dir, "..")
	}
	return null
}
