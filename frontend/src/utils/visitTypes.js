// Explicit mobile configuration per visit DocType (what metadata cannot express).
export const VISIT_TYPES = {
	"Site Visit": {
		listRoute: "SiteVisits",
		formRoute: "SiteVisit",
		icon: "map-pin",
		titleField: "customer_name",
		// Shown in the context card instead of the form steps.
		contextOnly: ["solar_proposal", "lead", "customer", "company", "currency", "lead_owner", "lead_source", "site_visit_by", "status"],
		title: (v) => v.customer_name || v.name,
		subtitle: (v) => [v.location, v.solar_proposal, v.requested_capacity_kw ? `${v.requested_capacity_kw} kW` : null].filter(Boolean).join(" · "),
		guidance: {},
	},
	"PMS Visit": {
		listRoute: "PMSVisits",
		formRoute: "PMSVisit",
		icon: "tool",
		titleField: "client_name",
		contextOnly: ["status", "service_person", "service_person_name", "project", "legacy_site_data_collection"],
		title: (v) => v.client_name || v.customer || v.name,
		subtitle: (v) => [v.place, v.project, v.plant_capacity_kw ? `${v.plant_capacity_kw} kW` : null].filter(Boolean).join(" · "),
		guidance: {
			ac_db_string_inverter: "Photograph the AC DB and string inverter together; make the labels readable.",
			inverter_name_plate: "Close-up of the inverter name plate so the model and serial number are readable.",
			ac_db: "Open AC DB showing breaker and SPD ratings.",
			dc_db: "Open DC DB showing fuse and SPD ratings.",
			panel_image: "Wide shot of the panel array showing its condition (dust, damage, shading).",
			house_image: "Front of the house so the site is easy to identify.",
			additional_image: "Anything else worth recording.",
		},
	},
}
