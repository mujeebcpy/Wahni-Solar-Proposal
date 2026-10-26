"""Bounded expressions and dependency-aware material rules, without Frappe or eval."""

import ast
import keyword
import math
import operator
import re
from collections.abc import Mapping
from dataclasses import dataclass


MAX_EXPRESSION_LENGTH = 2048
MAX_EXPRESSION_NODES = 256
MAX_EXPRESSION_DEPTH = 32
MAX_NUMERIC_MAGNITUDE = 1_000_000_000_000
MAX_STRING_LENGTH = 1024
MAX_MATERIAL_ROWS = 1000
MAX_TEMPLATE_MAPPINGS = 100
MAX_DEPENDENCY_DEPTH = 64

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_HELPERS = {"ceil", "floor", "round", "min", "max", "abs", "qty"}
_BINARY = {
	ast.Add: operator.add,
	ast.Sub: operator.sub,
	ast.Mult: operator.mul,
	ast.Div: operator.truediv,
	ast.FloorDiv: operator.floordiv,
	ast.Mod: operator.mod,
}
_COMPARE = {
	ast.Eq: operator.eq,
	ast.NotEq: operator.ne,
	ast.Lt: operator.lt,
	ast.LtE: operator.le,
	ast.Gt: operator.gt,
	ast.GtE: operator.ge,
}


class RuleError(ValueError):
	"""An invalid or unsupported staff-entered rule."""


@dataclass
class _Expression:
	text: str
	root: ast.AST
	variables: set
	quantities: set


def _valid_key(value):
	return isinstance(value, str) and bool(_IDENTIFIER.fullmatch(value)) and not keyword.iskeyword(value)


def _quantity_key(value):
	if not isinstance(value, str) or not 1 <= len(value.split(".")) <= 2:
		raise RuleError("qty() needs a literal rule key or template_alias.rule_key.")
	if not all(_valid_key(part) for part in value.split(".")):
		raise RuleError(f"Invalid quantity reference: {value!r}.")
	return value


def _scalar(value):
	if value is None or isinstance(value, bool):
		return value
	if type(value) in (int, float):
		if abs(value) > MAX_NUMERIC_MAGNITUDE or not math.isfinite(value):
			raise RuleError("Numeric values must be finite and no greater than 1 trillion in magnitude.")
		return value
	if isinstance(value, str) and len(value) <= MAX_STRING_LENGTH:
		return value
	raise RuleError("Expressions support only bounded numbers, strings, check values and empty values.")


def _number(value):
	if type(value) not in (int, float):
		raise RuleError("This expression requires a numeric value.")
	return _scalar(value)


def _quantity(value):
	value = _number(value)
	if value < 0:
		raise RuleError("Calculated quantities cannot be negative.")
	return value


def _boolean(value):
	if isinstance(value, bool):
		return value
	if type(value) in (int, float) and value in (0, 1):
		return bool(value)
	raise RuleError("A condition must return True, False, or a Check value (0 or 1).")


def _compile(expression, allowed_names=None, allow_qty=True):
	if not isinstance(expression, str) or not expression.strip():
		raise RuleError("Enter an expression.")
	text = expression.strip()
	if len(text) > MAX_EXPRESSION_LENGTH:
		raise RuleError(f"Expressions cannot exceed {MAX_EXPRESSION_LENGTH} characters.")
	try:
		root = ast.parse(text, mode="eval")
	except (SyntaxError, ValueError, RecursionError) as exc:
		raise RuleError(f"Invalid expression: {exc.msg if isinstance(exc, SyntaxError) else exc}.") from exc
	if sum(1 for _ in ast.walk(root)) > MAX_EXPRESSION_NODES:
		raise RuleError("Expression is too complex.")
	variables, quantities = set(), set()
	allowed = set(allowed_names) if allowed_names is not None else None

	def visit(node, depth=0):
		if depth > MAX_EXPRESSION_DEPTH:
			raise RuleError("Expression nesting is too deep.")
		children = []
		if isinstance(node, ast.Expression):
			children = [node.body]
		elif isinstance(node, ast.Constant):
			_scalar(node.value)
		elif isinstance(node, ast.Name):
			if not _valid_key(node.id) or node.id in _HELPERS:
				raise RuleError(f"Invalid variable name: {node.id}.")
			if allowed is not None and node.id not in allowed:
				raise RuleError(f"Unknown variable: {node.id}.")
			variables.add(node.id)
		elif isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
			children = [node.left, node.right]
		elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Not)):
			children = [node.operand]
		elif isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
			children = node.values
		elif isinstance(node, ast.Compare) and all(type(op) in _COMPARE for op in node.ops):
			children = [node.left, *node.comparators]
		elif isinstance(node, ast.IfExp):
			children = [node.test, node.body, node.orelse]
		elif isinstance(node, ast.Call):
			if not isinstance(node.func, ast.Name) or node.func.id not in _HELPERS or node.keywords:
				raise RuleError("Only approved helpers with positional arguments may be called.")
			name, args = node.func.id, node.args
			if name == "qty":
				if not allow_qty:
					raise RuleError("qty() is not allowed in this expression.")
				if len(args) != 1 or not isinstance(args[0], ast.Constant):
					raise RuleError("qty() requires exactly one literal string key.")
				quantities.add(_quantity_key(args[0].value))
			else:
				valid_count = (
					(name in {"ceil", "floor", "abs"} and len(args) == 1)
					or (name == "round" and 1 <= len(args) <= 2)
					or (name in {"min", "max"} and 1 <= len(args) <= 32)
				)
				if not valid_count:
					raise RuleError(f"Invalid number of arguments to {name}().")
				children = args
		else:
			raise RuleError(f"Unsupported expression syntax: {type(node).__name__}.")
		for child in children:
			visit(child, depth + 1)

	visit(root)
	return _Expression(text, root.body, variables, quantities)


def validate_expression(expr, allowed_names=None, allow_qty=True):
	"""Validate syntax and return referenced variable and literal quantity keys."""
	expression = _compile(expr, allowed_names, allow_qty)
	return {"variables": expression.variables, "quantities": expression.quantities}


def _run(expression, context, quantity_resolver=None):
	def resolve(node):
		if isinstance(node, ast.Constant):
			return _scalar(node.value)
		if isinstance(node, ast.Name):
			if node.id not in context:
				raise RuleError(f"Missing variable: {node.id}.")
			return _scalar(context[node.id])
		if isinstance(node, ast.BinOp):
			return _scalar(_BINARY[type(node.op)](_number(resolve(node.left)), _number(resolve(node.right))))
		if isinstance(node, ast.UnaryOp):
			value = resolve(node.operand)
			if isinstance(node.op, ast.Not):
				return not _boolean(value)
			return _scalar(_number(value) if isinstance(node.op, ast.UAdd) else -_number(value))
		if isinstance(node, ast.BoolOp):
			for child in node.values:
				value = _boolean(resolve(child))
				if isinstance(node.op, ast.And) and not value:
					return False
				if isinstance(node.op, ast.Or) and value:
					return True
			return value
		if isinstance(node, ast.Compare):
			left = resolve(node.left)
			for op, child in zip(node.ops, node.comparators, strict=True):
				right = resolve(child)
				if not _COMPARE[type(op)](left, right):
					return False
				left = right
			return True
		if isinstance(node, ast.IfExp):
			return resolve(node.body if _boolean(resolve(node.test)) else node.orelse)
		if isinstance(node, ast.Call):
			name = node.func.id
			if name == "qty":
				if quantity_resolver is None:
					raise RuleError("qty() requires a material quantity resolver.")
				key = node.args[0].value
				try:
					return _quantity(quantity_resolver(key))
				except LookupError as exc:
					raise RuleError(f"Unknown quantity reference: {key}.") from exc
			args = [_number(resolve(arg)) for arg in node.args]
			if name == "round":
				if len(args) == 2 and (type(args[1]) is not int or not -12 <= args[1] <= 12):
					raise RuleError("round() precision must be an integer between -12 and 12.")
				return _scalar(round(*args))
			if name in {"min", "max"}:
				return _scalar((min if name == "min" else max)(args))
			return _scalar({"ceil": math.ceil, "floor": math.floor, "abs": abs}[name](*args))
		raise RuleError("Unsupported expression.")

	try:
		value = _scalar(resolve(expression.root))
		if type(value) in (int, float):
			_quantity(value)
		return value
	except RuleError:
		raise
	except (ArithmeticError, TypeError, ValueError, RecursionError) as exc:
		raise RuleError(f"Cannot calculate expression: {exc}.") from exc


def evaluate(expr, context, quantity_resolver=None):
	"""Evaluate one approved scalar expression against already typed input values."""
	if not isinstance(context, Mapping):
		raise RuleError("Expression context must be a mapping of variable names to values.")
	return _run(_compile(expr, context), context, quantity_resolver)


def _enabled(value, default=True):
	if value is None or value == "":
		return default
	if value in (True, 1, "1"):
		return True
	if value in (False, 0, "0"):
		return False
	raise RuleError("Enabled flags must be Check values (0 or 1).")


def evaluate_materials(mappings, context, overrides=None, *, include_excluded=False):
	"""Calculate rows, honoring optional templates and effective quantity overrides.

	``qty('key')`` references the current template instance. ``qty('alias.key')``
	references another mapping. Known excluded quantities are zero; unknown keys
	and cycles are errors even when hidden in an unselected conditional branch.
	An override is ``{'alias.key': {'quantity': 10, 'reason': 'Site measurement'}}``.
	The overridden value is visible to every downstream quantity expression.
	``include_excluded`` adds zero/excluded rows and inclusion diagnostics for a
	staff preview, while normal generation emits only effective material rows.
	"""
	if not isinstance(context, Mapping):
		raise RuleError("Material context must be a mapping.")
	mappings = list(mappings)
	if len(mappings) > MAX_TEMPLATE_MAPPINGS:
		raise RuleError("Too many template mappings in this package.")
	aliases, rows, graph = {}, {}, {}

	def expression(value, default="True"):
		if value is not None and not isinstance(value, str):
			raise RuleError("Expressions must be entered as text.")
		return _compile(value if isinstance(value, str) and value.strip() else default, context)

	for mapping in mappings:
		if not isinstance(mapping, Mapping):
			raise RuleError("Each template mapping must be a mapping of field names to values.")
		alias = mapping.get("template_alias")
		if not _valid_key(alias) or alias in aliases:
			raise RuleError(f"Template alias must be a unique stable name: {alias!r}.")
		template = mapping.get("template") or {}
		if not isinstance(template, Mapping):
			raise RuleError(f"Template {alias} must contain a mapping of field names to values.")
		aliases[alias] = {
			"template": template,
			"enabled": _enabled(mapping.get("enabled")) and not _enabled(template.get("disabled"), False),
			"condition": expression(mapping.get("include_when")),
			"validation": expression(template.get("validation_condition")),
		}
		for item in template.get("items") or []:
			if len(rows) >= MAX_MATERIAL_ROWS:
				raise RuleError("Too many material rules in this package.")
			if not isinstance(item, Mapping):
				raise RuleError(f"Template {alias} material rows must contain named fields.")
			key = item.get("rule_key")
			qualified = f"{alias}.{key}"
			if not _valid_key(key) or qualified in rows:
				raise RuleError(f"Material rule key must be a unique stable name in {alias}: {key!r}.")
			rows[qualified] = {
				"alias": alias,
				"item": item,
				"enabled": _enabled(item.get("enabled")),
				"condition": expression(item.get("include_when")),
				"formula": expression(item.get("quantity_formula"), "0"),
			}

	def qualified_key(alias, key):
		qualified = key if "." in key else f"{alias}.{key}"
		if qualified not in rows:
			raise RuleError(f"Unknown quantity reference: {qualified}.")
		return qualified

	def quantity_dependencies(alias, *expressions):
		return {qualified_key(alias, key) for expr in expressions for key in expr.quantities}

	for alias, mapping in aliases.items():
		graph[(alias, "include")] = quantity_dependencies(alias, mapping["condition"])
		graph[(alias, "validate")] = {(alias, "include")} | quantity_dependencies(alias, mapping["validation"])
	for key, row in rows.items():
		alias = row["alias"]
		graph[key] = {(alias, "include"), (alias, "validate")} | quantity_dependencies(
			alias, row["condition"], row["formula"]
		)

	visited, visiting = {}, set()

	def check_graph(key, depth=0):
		if key in visiting:
			raise RuleError(f"Quantity dependency cycle involving {key}.")
		if depth > MAX_DEPENDENCY_DEPTH:
			raise RuleError("Quantity dependency chain is too deep.")
		if key in visited:
			if depth + visited[key] > MAX_DEPENDENCY_DEPTH:
				raise RuleError("Quantity dependency chain is too deep.")
			return visited[key]
		visiting.add(key)
		height = 0
		for dependency in graph[key]:
			height = max(height, 1 + check_graph(dependency, depth + 1))
		visiting.remove(key)
		visited[key] = height
		return height

	for key in graph:
		check_graph(key)

	if overrides is not None and not isinstance(overrides, Mapping):
		raise RuleError("Quantity overrides must be keyed by template_alias.rule_key.")
	normalized_overrides = {}
	for key, override in (overrides or {}).items():
		if key not in rows:
			raise RuleError(f"Unknown quantity override: {key}.")
		if not isinstance(override, Mapping):
			raise RuleError(f"Invalid quantity override for {key}.")
		reason = override.get("reason", override.get("override_reason", ""))
		if not isinstance(reason, str) or not reason.strip():
			raise RuleError(f"Enter a reason for the quantity override on {key}.")
		normalized_overrides[key] = {"quantity": _quantity(override.get("quantity")), "reason": reason.strip()}

	cache, result_info = {}, {}

	def run_at(expr, alias, label, quantities=None):
		def resolve_reference(key):
			value = resolve(qualified_key(alias, key))
			if quantities is not None:
				quantities[key] = value
			return value

		try:
			return _run(expr, context, resolve_reference)
		except RuleError as exc:
			raise RuleError(f"{label}: {exc}") from exc

	def resolve(key):
		if key in cache:
			return cache[key]
		if isinstance(key, tuple):
			alias, kind = key
			mapping = aliases[alias]
			if kind == "include":
				value = mapping["enabled"] and _boolean(
					run_at(mapping["condition"], alias, f"Template {alias} Include When")
				)
			else:
				value = True
				if resolve((alias, "include")):
					value = _boolean(run_at(mapping["validation"], alias, f"Template {alias} validation"))
					if not value:
						raise RuleError(
							f"Template {alias}: "
							+ (mapping["template"].get("validation_message") or "Selected inputs are unsupported.")
						)
		else:
			row, quantities = rows[key], {}
			alias = row["alias"]
			exclusion = ""
			included = row["enabled"] and resolve((alias, "include"))
			if not included:
				if not row["enabled"]:
					exclusion = "Material rule is disabled."
				elif not aliases[alias]["enabled"]:
					exclusion = f"Template {alias} is disabled."
				else:
					exclusion = f"Template {alias} Include When ({aliases[alias]['condition'].text}) is false."
			if included:
				resolve((alias, "validate"))
				included = _boolean(run_at(row["condition"], alias, f"{key} Include When"))
				if not included:
					exclusion = f"Include When ({row['condition'].text}) is false."
			generated = 0
			if included:
				if not (row["item"].get("quantity_formula") or "").strip():
					raise RuleError(f"{key}: enter a Quantity Formula.")
				generated = _quantity(run_at(row["formula"], alias, key, quantities))
			override = normalized_overrides.get(key) if included else None
			value = override["quantity"] if override else generated
			result_info[key] = {
				"generated": generated,
				"override": override,
				"included": included,
				"quantities": quantities,
				"exclusion": exclusion,
			}
		cache[key] = value
		return value

	# Validate active templates even when they currently have no material rows.
	for alias in aliases:
		resolve((alias, "validate"))
	result = []
	for key, row in rows.items():
		quantity = resolve(key)
		info = result_info[key]
		if not include_excluded and (not info["included"] or (quantity == 0 and not info["override"])):
			continue
		item, alias = row["item"], row["alias"]
		template = aliases[alias]["template"]
		variables = ", ".join(f"{name}={context[name]!r}" for name in sorted(row["formula"].variables))
		dependencies = ", ".join(f"qty({name!r})={value}" for name, value in info["quantities"].items())
		note = info["exclusion"] or f"{row['formula'].text} = {info['generated']}"
		if substitutions := ", ".join(part for part in (variables, dependencies) if part):
			note += f" ({substitutions})"
		if info["override"]:
			note += f"; site override = {quantity}: {info['override']['reason']}"
		result_row = {
			"source_template": template.get("name"),
			"template_alias": alias,
			"rule_key": item["rule_key"],
			"component_group": template.get("group_name") or "",
			"component_label": item.get("component_label") or "",
			"item_code": item.get("item_code"),
			"uom": item.get("uom"),
			"description": item.get("description") or "",
			"quantity": quantity,
			"generated_quantity": info["generated"],
			"calculation_note": note,
			"has_quantity_override": bool(info["override"]),
			"override_reason": info["override"]["reason"] if info["override"] else "",
		}
		if include_excluded:
			result_row["included"] = bool(info["included"])
		result.append(result_row)
	return result
