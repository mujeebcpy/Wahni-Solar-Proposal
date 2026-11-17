// __("Text {0}", [value]) using translations from the Frappe boot.
export function translate(text, replace, messages) {
	const source = messages ?? window.frappe?.boot?.__messages ?? {}
	let translated = source[text] || text
	if (replace && typeof replace === "object") {
		translated = translated.replace(/{(\d+)}/g, (match, index) =>
			replace[index] !== undefined ? replace[index] : match
		)
	}
	return translated
}

export const __ = (text, replace) => translate(text, replace)

export default {
	install(app) {
		app.config.globalProperties.__ = __
		app.provide("__", __)
	},
}
