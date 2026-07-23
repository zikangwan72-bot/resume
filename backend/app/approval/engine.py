from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Any

from app.approval.schemas import APPROVAL_TYPES, BUSINESS_FIELD_TYPES, FIELD_TYPES, DefinitionError

COMPARABLE_FIELD_TYPES = {"number", "money", "text", "textarea", "radio", "select"}
CONDITION_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "contains", "not_contains"}
NODE_TYPES = {"start", "approval", "countersign", "condition", "end"}
APPROVAL_NODE_TYPES = {"approval", "countersign"}


def compare_value(actual: object, operator: str, expected: object) -> bool:
    operations = {
        "eq": lambda a, b: a == b,
        "ne": lambda a, b: a != b,
        "gt": lambda a, b: a > b,
        "gte": lambda a, b: a >= b,
        "lt": lambda a, b: a < b,
        "lte": lambda a, b: a <= b,
        "contains": lambda a, b: str(b) in str(a),
        "not_contains": lambda a, b: str(b) not in str(a),
    }
    try:
        return operations[operator](actual, expected)
    except (KeyError, TypeError):
        return False


def validate_process_definition(
    form_schema: dict[str, Any], flow_schema: dict[str, Any], active_user_ids: Iterable[str]
) -> list[DefinitionError]:
    errors: list[DefinitionError] = []
    active_users = set(active_user_ids) if isinstance(active_user_ids, Iterable) else set()
    fields = _validation_items(
        form_schema, "fields", "invalid_fields_section", "表单 fields 必须是列表", errors
    )
    nodes = _validation_items(
        flow_schema, "nodes", "invalid_nodes_section", "流程 nodes 必须是列表", errors
    )
    edges = _validation_items(
        flow_schema, "edges", "invalid_edges_section", "流程 edges 必须是列表", errors
    )

    field_types = _validate_fields(fields, errors)
    if not any(field_type in BUSINESS_FIELD_TYPES for field_type in field_types.values()):
        errors.append(_error("missing_business_field", "流程至少需要一个业务表单字段"))
    node_ids, nodes_by_id = _validate_nodes(nodes, active_users, errors)
    valid_edges = _validate_edges(edges, node_ids, errors)

    starts = [node_id for node_id, node in nodes_by_id.items() if node.get("type") == "start"]
    ends = [node_id for node_id, node in nodes_by_id.items() if node.get("type") == "end"]
    if not starts:
        errors.append(_error("missing_start_node", "流程必须包含一个开始节点"))
    elif len(starts) > 1:
        errors.append(_error("multiple_start_nodes", "流程只能包含一个开始节点"))
    if not ends:
        errors.append(_error("missing_end_node", "流程必须包含一个结束节点"))
    elif len(ends) > 1:
        errors.append(_error("multiple_end_nodes", "流程只能包含一个结束节点"))
    if not any(node.get("type") in APPROVAL_NODE_TYPES for node in nodes_by_id.values()):
        errors.append(_error("missing_approval_node", "流程至少需要一个审批节点"))

    outgoing = _adjacency(valid_edges)
    _validate_outgoing_edges(nodes_by_id, outgoing, errors)
    if starts:
        reachable = _reachable(starts[0], outgoing)
        for node_id in node_ids:
            if node_id not in reachable:
                errors.append(_error("disconnected_node", "节点未连接到开始节点", node_id))
    else:
        reachable = set()

    if _has_cycle(node_ids, outgoing):
        errors.append(_error("flow_cycle", "流程图不能包含环路"))

    _validate_condition_edges(nodes_by_id, outgoing, field_types, errors)
    if ends and starts:
        _validate_end_reachability(node_ids, starts[0], ends[0], outgoing, errors)

    return errors


def resolve_execution_path(
    form_data: dict[str, Any], flow_schema: dict[str, Any]
) -> list[dict[str, Any]]:
    if not isinstance(form_data, dict):
        raise ValueError("form_data must be an object")
    nodes = _items(flow_schema, "nodes")
    edges = _items(flow_schema, "edges")
    if not all(isinstance(node, dict) for node in nodes):
        raise ValueError("flow_schema contains a malformed node")
    if not all(isinstance(edge, dict) for edge in edges):
        raise ValueError("flow_schema contains a malformed edge")

    nodes_by_id = {node.get("id"): node for node in nodes if _valid_id(node.get("id"))}
    if len(nodes_by_id) != len(nodes):
        raise ValueError("flow_schema nodes require unique non-empty IDs")
    start = next(
        (node_id for node_id, node in nodes_by_id.items() if node.get("type") == "start"), None
    )
    if start is None:
        raise ValueError("flow_schema requires a start node")

    outgoing = _adjacency(_runtime_edges(edges, nodes_by_id))
    current = start
    visited: set[str] = set()
    path: list[dict[str, Any]] = []

    while True:
        if current in visited:
            raise ValueError("flow_schema contains a cycle")
        visited.add(current)
        node = nodes_by_id[current]
        if node.get("type") in APPROVAL_NODE_TYPES:
            path.append(node)
        if node.get("type") == "end":
            return path

        next_edge = _next_edge(node, outgoing.get(current, []), form_data)
        if next_edge is None:
            raise ValueError(f"node {current!r} has no executable outgoing edge")
        current = next_edge["target"]


def _items(schema: dict[str, Any], key: str) -> list[dict[str, Any]]:
    if not isinstance(schema, dict) or not isinstance(schema.get(key), list):
        raise ValueError(f"schema section {key!r} must be a list")
    return schema[key]


def _validation_items(
    schema: object,
    key: str,
    code: str,
    message: str,
    errors: list[DefinitionError],
) -> list[Any]:
    if not isinstance(schema, dict) or not isinstance(schema.get(key), list):
        errors.append(_error(code, message))
        return []
    return schema[key]


def _validate_fields(
    fields: list[Any], errors: list[DefinitionError]
) -> dict[str, object]:
    field_types: dict[str, object] = {}
    field_ids: set[str] = set()
    for field in fields:
        if not isinstance(field, dict):
            errors.append(_error("invalid_field_definition", "表单字段必须是对象"))
            continue
        field_id = field.get("id")
        if not _valid_id(field_id):
            errors.append(_error("invalid_field_id", "表单字段必须使用非空稳定 ID"))
            continue
        elif field_id in field_ids:
            errors.append(_error("duplicate_field_id", "表单字段 ID 不能重复", field_id))
            continue
        field_ids.add(field_id)
        field_type = field.get("type")
        if not isinstance(field_type, str) or field_type not in FIELD_TYPES:
            errors.append(_error("invalid_field_type", "表单字段类型不受支持", field_id))
            continue
        if field_type in {"radio", "select", "checkbox"} and not _valid_choice_options(
            field.get("options")
        ):
            errors.append(
                _error(
                    "invalid_choice_options",
                    "选择字段必须配置非空、不重复的标量选项",
                    field_id,
                )
            )
        field_types[field_id] = field_type
    return field_types


def _valid_choice_options(options: object) -> bool:
    if not isinstance(options, list) or not options:
        return False

    seen: set[tuple[type, object]] = set()
    for option in options:
        if not isinstance(option, str | int | float | bool):
            return False
        if isinstance(option, str) and not option.strip():
            return False
        key = (type(option), option)
        if key in seen:
            return False
        seen.add(key)
    return True


def _validate_nodes(
    nodes: list[Any], active_users: set[str], errors: list[DefinitionError]
) -> tuple[set[str], dict[str, dict[str, Any]]]:
    node_ids: set[str] = set()
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            errors.append(_error("invalid_node_definition", "流程节点必须是对象"))
            continue
        node_id = node.get("id")
        if not _valid_id(node_id):
            errors.append(_error("invalid_node_id", "流程节点必须使用非空稳定 ID"))
            continue
        if node_id in node_ids:
            errors.append(_error("duplicate_node_id", "流程节点 ID 不能重复", node_id))
            continue
        node_ids.add(node_id)
        nodes_by_id[node_id] = node
        if node.get("type") not in NODE_TYPES:
            errors.append(_error("unknown_node_type", "流程节点类型不受支持", node_id))
        elif node.get("type") in APPROVAL_NODE_TYPES:
            _validate_approvers(node, active_users, errors)
    return node_ids, nodes_by_id


def _validate_approvers(
    node: dict[str, Any], active_users: set[str], errors: list[DefinitionError]
) -> None:
    node_id = node["id"]
    approval_type = node.get("approval_type", node.get("subtype", node.get("mode", "single")))
    if not isinstance(approval_type, str) or approval_type not in APPROVAL_TYPES:
        errors.append(_error("invalid_approval_type", "审批节点模式不受支持", node_id))
        return
    if node.get("type") == "countersign" or approval_type == "counter_sign":
        approver_ids = node.get("approver_ids")
        if not isinstance(approver_ids, list) or not all(
            _valid_id(value) for value in approver_ids
        ):
            errors.append(
                _error("invalid_countersign_approvers", "会签节点至少需要两名不同审批人", node_id)
            )
            return
        if len(approver_ids) < 2 or len(set(approver_ids)) != len(approver_ids):
            errors.append(
                _error("invalid_countersign_approvers", "会签节点至少需要两名不同审批人", node_id)
            )
        for approver_id in approver_ids:
            if approver_id not in active_users:
                errors.append(_error("inactive_approver", "审批人必须是启用员工", node_id))
    else:
        approver_id = node.get("approver_id")
        if not _valid_id(approver_id) or approver_id not in active_users:
            errors.append(_error("inactive_approver", "审批人必须是启用员工", node_id))


def _validate_edges(
    edges: list[Any], node_ids: set[str], errors: list[DefinitionError]
) -> list[dict[str, Any]]:
    valid_edges: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            errors.append(_error("invalid_edge_definition", "流程连线必须是对象"))
            continue
        source, target = edge.get("source"), edge.get("target")
        if not _valid_id(source) or not _valid_id(target):
            errors.append(_error("invalid_edge_definition", "流程连线必须引用稳定节点 ID"))
            continue
        if source not in node_ids or target not in node_ids:
            errors.append(_error("unknown_edge_node", "连线引用了不存在的节点"))
            continue
        valid_edges.append(edge)
    return valid_edges


def _validate_outgoing_edges(
    nodes_by_id: dict[str, dict[str, Any]],
    outgoing: dict[str, list[dict[str, Any]]],
    errors: list[DefinitionError],
) -> None:
    for node_id, node in nodes_by_id.items():
        edge_count = len(outgoing.get(node_id, []))
        if node.get("type") == "end":
            if edge_count:
                errors.append(_error("invalid_end_outgoing", "结束节点不能有出边", node_id))
        elif node.get("type") != "condition" and edge_count != 1:
            errors.append(
                _error("invalid_non_condition_branch", "非条件节点必须有且仅有一条出边", node_id)
            )


def _validate_condition_edges(
    nodes_by_id: dict[str, dict[str, Any]],
    outgoing: dict[str, list[dict[str, Any]]],
    field_types: dict[str, object],
    errors: list[DefinitionError],
) -> None:
    for node_id, node in nodes_by_id.items():
        if node.get("type") != "condition":
            continue
        condition_edges = outgoing.get(node_id, [])
        default_edges = [edge for edge in condition_edges if _is_default_edge(edge)]
        if not default_edges:
            errors.append(_error("missing_default_branch", "条件节点必须包含默认分支", node_id))
        elif len(default_edges) > 1:
            errors.append(
                _error("multiple_default_branches", "条件节点只能包含一个默认分支", node_id)
            )
        if not any(not _is_default_edge(edge) for edge in condition_edges):
            errors.append(
                _error("missing_condition_branch", "条件节点至少需要一个条件分支", node_id)
            )
        for edge in condition_edges:
            if _is_default_edge(edge):
                continue
            condition = edge.get("condition")
            if not isinstance(condition, dict):
                errors.append(_error("invalid_condition", "条件分支必须配置条件", node_id))
                continue
            field_id = condition.get("field_id", condition.get("field"))
            operator = condition.get("operator")
            if not _valid_id(field_id) or not isinstance(operator, str):
                errors.append(_error("invalid_condition", "条件分支配置格式无效", node_id))
                continue
            if not _has_comparison_value(condition):
                errors.append(_error("missing_condition_value", "条件分支必须配置比较值", node_id))
            if field_id not in field_types:
                errors.append(_error("unknown_condition_field", "条件引用的字段不存在", node_id))
            elif field_types[field_id] not in COMPARABLE_FIELD_TYPES:
                errors.append(
                    _error("invalid_condition_field_type", "条件引用的字段类型不可比较", node_id)
                )
            if operator not in CONDITION_OPERATORS:
                errors.append(_error("invalid_condition_operator", "条件比较方式无效", node_id))


def _validate_end_reachability(
    node_ids: set[str],
    start: str,
    end: str,
    outgoing: dict[str, list[dict[str, Any]]],
    errors: list[DefinitionError],
) -> None:
    reverse = _reverse_adjacency(outgoing)
    can_reach_end = _reachable(end, reverse)
    for node_id in _reachable(start, outgoing):
        if node_id not in can_reach_end:
            errors.append(_error("path_does_not_reach_end", "从该节点无法到达结束节点", node_id))


def _next_edge(
    node: dict[str, Any], edges: list[dict[str, Any]], form_data: dict[str, Any]
) -> dict[str, Any] | None:
    if node.get("type") != "condition":
        return edges[0] if edges else None
    default_edge: dict[str, Any] | None = None
    for edge in edges:
        if _is_default_edge(edge):
            default_edge = edge
            continue
        condition = edge.get("condition")
        if not isinstance(condition, dict):
            raise ValueError("flow_schema contains a malformed condition")
        field_id = condition.get("field_id", condition.get("field"))
        if (
            not _valid_id(field_id)
            or not isinstance(condition.get("operator"), str)
            or not _has_comparison_value(condition)
        ):
            raise ValueError("flow_schema contains a malformed condition")
        expected = condition.get("value", condition.get("expected"))
        if compare_value(form_data.get(field_id), condition.get("operator", ""), expected):
            return edge
    return default_edge


def _runtime_edges(
    edges: list[dict[str, Any]], nodes_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    valid_edges: list[dict[str, Any]] = []
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if not _valid_id(source) or not _valid_id(target):
            raise ValueError("flow_schema contains a malformed edge")
        if source not in nodes_by_id or target not in nodes_by_id:
            raise ValueError("flow_schema edge references an unknown node")
        if nodes_by_id[source].get("type") == "condition" and not _is_default_edge(edge):
            condition = edge.get("condition")
            if not isinstance(condition, dict):
                raise ValueError("flow_schema contains a malformed condition")
            field_id = condition.get("field_id", condition.get("field"))
            if (
                not _valid_id(field_id)
                or not isinstance(condition.get("operator"), str)
                or not _has_comparison_value(condition)
            ):
                raise ValueError("flow_schema contains a malformed condition")
        valid_edges.append(edge)
    return valid_edges


def _adjacency(edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        result.setdefault(edge["source"], []).append(edge)
    return result


def _reverse_adjacency(
    outgoing: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for source, edges in outgoing.items():
        for edge in edges:
            result.setdefault(edge["target"], []).append({"target": source})
    return result


def _reachable(start: str, outgoing: dict[str, list[dict[str, Any]]]) -> set[str]:
    seen: set[str] = set()
    pending = deque([start])
    while pending:
        current = pending.popleft()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(edge["target"] for edge in outgoing.get(current, []))
    return seen


def _has_cycle(node_ids: set[str], outgoing: dict[str, list[dict[str, Any]]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for edge in outgoing.get(node_id, []):
            if visit(edge["target"]):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in node_ids)


def _is_default_edge(edge: dict[str, Any]) -> bool:
    return edge.get("default") is True or edge.get("is_default") is True


def _has_comparison_value(condition: dict[str, Any]) -> bool:
    return "value" in condition or "expected" in condition


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _error(code: str, message: str, target_id: str | None = None) -> DefinitionError:
    return DefinitionError(code=code, message=message, target_id=target_id)
