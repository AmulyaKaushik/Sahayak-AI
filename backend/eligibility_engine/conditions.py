"""Deterministic condition-tree evaluator. No LLM involvement anywhere here.

A condition node is either:
  - a leaf:  {"id": "income_requirement", "field": "monthly_income", "op": "<=", "value": 60000}
  - a group: {"op": "AND" | "OR", "conditions": [<node>, ...]}

EligibilityRule.conditions (Section 5) is a list[dict] of top-level nodes,
implicitly AND-ed together.

Evaluation is tri-state per leaf: True (met), False (known and not met), or
None (the field isn't known yet -- can't be evaluated). AND/OR propagate the
tri-state per standard three-valued logic so that "unknown" never silently
becomes "eligible".
"""

from typing import Any

_OPS = {
    "==": lambda field_value, value: field_value == value,
    "!=": lambda field_value, value: field_value != value,
    "<": lambda field_value, value: field_value < value,
    "<=": lambda field_value, value: field_value <= value,
    ">": lambda field_value, value: field_value > value,
    ">=": lambda field_value, value: field_value >= value,
    "in": lambda field_value, value: value in field_value,
    "not_in": lambda field_value, value: value not in field_value,
}


def _is_leaf(node: dict) -> bool:
    return "field" in node


def evaluate_leaf(node: dict, known_fields: dict[str, Any]) -> bool | None:
    field_name = node["field"]
    if field_name not in known_fields or known_fields[field_name] is None:
        return None

    op = _OPS[node["op"]]
    return bool(op(known_fields[field_name], node["value"]))


def evaluate_node(node: dict, known_fields: dict[str, Any]) -> bool | None:
    if _is_leaf(node):
        return evaluate_leaf(node, known_fields)

    child_results = [evaluate_node(child, known_fields) for child in node["conditions"]]

    if node["op"] == "AND":
        if any(result is False for result in child_results):
            return False
        if any(result is None for result in child_results):
            return None
        return True

    if node["op"] == "OR":
        if any(result is True for result in child_results):
            return True
        if any(result is None for result in child_results):
            return None
        return False

    raise ValueError(f"Unknown logical operator: {node['op']}")


def evaluate_tree(nodes: list[dict], known_fields: dict[str, Any]) -> bool | None:
    """Top-level list of nodes, implicitly AND-ed together."""
    return evaluate_node({"op": "AND", "conditions": nodes}, known_fields)


def collect_leaves(nodes: list[dict]) -> list[dict]:
    leaves: list[dict] = []
    for node in nodes:
        if _is_leaf(node):
            leaves.append(node)
        else:
            leaves.extend(collect_leaves(node["conditions"]))
    return leaves
