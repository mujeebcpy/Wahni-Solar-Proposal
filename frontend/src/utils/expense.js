// Client-side checks mirror the server so users see problems inline;
// the server (HRMS + portal API) remains authoritative.
export function validateClaim(form, { approverRequired = false } = {}) {
	const errors = {}
	if (!form.posting_date) errors.posting_date = "Choose the claim date."
	if (approverRequired && !form.expense_approver) errors.expense_approver = "Select an expense approver."
	if (!form.expenses.length) errors.expenses = "Add at least one expense."
	form.expenses.forEach((item, index) => {
		if (!item.expense_type) errors[`expenses.${index}`] = "Choose an expense type."
		else if (!(Number(item.amount) > 0)) errors[`expenses.${index}`] = "Enter an amount greater than zero."
		else if (!item.expense_date) errors[`expenses.${index}`] = "Choose a date."
	})
	return errors
}
