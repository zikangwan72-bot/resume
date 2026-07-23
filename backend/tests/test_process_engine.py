import pytest

from app.approval.engine import resolve_execution_path, validate_process_definition

FORM_SCHEMA = {
    "fields": [
        {"id": "amount", "label": "金额", "type": "money"},
        {"id": "purpose", "label": "用途", "type": "text"},
    ]
}

FLOW_WITH_AMOUNT_BRANCH = {
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "manager", "type": "approval", "approval_type": "single", "approver_id": "u1"},
        {"id": "amount_gate", "type": "condition"},
        {"id": "director", "type": "approval", "approval_type": "single", "approver_id": "u2"},
        {"id": "finance", "type": "approval", "approval_type": "single", "approver_id": "u3"},
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"source": "start", "target": "manager"},
        {"source": "manager", "target": "amount_gate"},
        {
            "source": "amount_gate",
            "target": "director",
            "condition": {"field_id": "amount", "operator": "gte", "value": 100000},
        },
        {"source": "amount_gate", "target": "finance", "default": True},
        {"source": "director", "target": "finance"},
        {"source": "finance", "target": "end"},
    ],
}


def _error_codes(
    form_schema: dict, flow_schema: dict, active_users: set[str] | None = None
) -> set[str]:
    active_users = active_users or {"u1", "u2", "u3"}
    return {
        error.code for error in validate_process_definition(form_schema, flow_schema, active_users)
    }


def test_amount_condition_selects_high_value_branch():
    path = resolve_execution_path({"amount": 120000}, FLOW_WITH_AMOUNT_BRANCH)

    assert [node["id"] for node in path] == ["manager", "director", "finance"]


def test_conditions_use_declared_edge_order_before_default_branch():
    flow = {
        **FLOW_WITH_AMOUNT_BRANCH,
        "edges": [
            *FLOW_WITH_AMOUNT_BRANCH["edges"][:2],
            {
                "source": "amount_gate",
                "target": "finance",
                "condition": {"field_id": "amount", "operator": "gte", "value": 50000},
            },
            *FLOW_WITH_AMOUNT_BRANCH["edges"][2:],
        ],
    }

    path = resolve_execution_path({"amount": 120000}, flow)

    assert [node["id"] for node in path] == ["manager", "finance"]


def test_validator_rejects_cycle_and_inactive_approver():
    cyclic_flow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {
                "id": "manager",
                "type": "approval",
                "approval_type": "single",
                "approver_id": "inactive",
            },
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "manager"},
            {"source": "manager", "target": "start"},
            {"source": "manager", "target": "end"},
        ],
    }

    errors = validate_process_definition(FORM_SCHEMA, cyclic_flow, {"active-user"})

    assert {"flow_cycle", "inactive_approver"} <= {error.code for error in errors}


def test_default_branch_is_required():
    flow_without_default = {
        **FLOW_WITH_AMOUNT_BRANCH,
        "edges": [
            edge
            for edge in FLOW_WITH_AMOUNT_BRANCH["edges"]
            if not (edge["source"] == "amount_gate" and edge.get("default"))
        ],
    }

    assert "missing_default_branch" in _error_codes(FORM_SCHEMA, flow_without_default)


@pytest.mark.parametrize(
    ("form_schema", "flow_schema", "expected_code"),
    [
        (
            {"fields": [{"id": "amount", "type": "money"}, {"id": "amount", "type": "money"}]},
            FLOW_WITH_AMOUNT_BRANCH,
            "duplicate_field_id",
        ),
        (
            FORM_SCHEMA,
            {
                **FLOW_WITH_AMOUNT_BRANCH,
                "nodes": [
                    {**node, "id": ""} if node["id"] == "manager" else node
                    for node in FLOW_WITH_AMOUNT_BRANCH["nodes"]
                ],
            },
            "invalid_node_id",
        ),
        (
            FORM_SCHEMA,
            {
                **FLOW_WITH_AMOUNT_BRANCH,
                "edges": [
                    {**edge, "target": "missing"} if edge["source"] == "start" else edge
                    for edge in FLOW_WITH_AMOUNT_BRANCH["edges"]
                ],
            },
            "unknown_edge_node",
        ),
        (
            FORM_SCHEMA,
            {
                **FLOW_WITH_AMOUNT_BRANCH,
                "edges": [
                    {
                        **edge,
                        "condition": {"field_id": "absent", "operator": "eq", "value": 1},
                    }
                    if edge["source"] == "amount_gate" and edge.get("condition")
                    else edge
                    for edge in FLOW_WITH_AMOUNT_BRANCH["edges"]
                ],
            },
            "unknown_condition_field",
        ),
        (
            {"fields": [{"id": "amount", "type": "attachment"}]},
            FLOW_WITH_AMOUNT_BRANCH,
            "invalid_condition_field_type",
        ),
    ],
)
def test_validator_rejects_unstable_ids_and_invalid_references(
    form_schema, flow_schema, expected_code
):
    assert expected_code in _error_codes(form_schema, flow_schema)


def test_validator_rejects_disconnected_nodes():
    disconnected_flow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "end", "type": "end"},
            {"id": "orphan", "type": "approval", "approval_type": "single", "approver_id": "u1"},
        ],
        "edges": [{"source": "start", "target": "end"}],
    }

    codes = _error_codes(FORM_SCHEMA, disconnected_flow)

    assert "disconnected_node" in codes


def test_validator_requires_at_least_one_approval_node():
    flow = {
        "nodes": [{"id": "start", "type": "start"}, {"id": "end", "type": "end"}],
        "edges": [{"source": "start", "target": "end"}],
    }

    assert "missing_approval_node" in _error_codes(FORM_SCHEMA, flow)


def test_validator_requires_at_least_two_active_countersign_approvers():
    flow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {
                "id": "signers",
                "type": "approval",
                "approval_type": "counter_sign",
                "approver_ids": ["u1"],
            },
            {"id": "end", "type": "end"},
        ],
        "edges": [{"source": "start", "target": "signers"}, {"source": "signers", "target": "end"}],
    }

    assert "invalid_countersign_approvers" in _error_codes(FORM_SCHEMA, flow)


def test_validator_rejects_paths_that_cannot_reach_end():
    flow = {
        **FLOW_WITH_AMOUNT_BRANCH,
        "nodes": [
            *FLOW_WITH_AMOUNT_BRANCH["nodes"],
            {"id": "dead_end", "type": "approval", "approval_type": "single", "approver_id": "u1"},
        ],
        "edges": [
            *FLOW_WITH_AMOUNT_BRANCH["edges"],
            {"source": "amount_gate", "target": "dead_end", "default": True},
        ],
    }

    assert "path_does_not_reach_end" in _error_codes(FORM_SCHEMA, flow)


@pytest.mark.parametrize(
    ("flow", "expected_code"),
    [
        (
            {
                "nodes": [
                    {"id": "approval", "type": "approval", "approver_id": "u1"},
                    {"id": "end", "type": "end"},
                ],
                "edges": [{"source": "approval", "target": "end"}],
            },
            "missing_start_node",
        ),
        (
            {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "second_start", "type": "start"},
                    {"id": "approval", "type": "approval", "approver_id": "u1"},
                    {"id": "end", "type": "end"},
                ],
                "edges": [
                    {"source": "start", "target": "approval"},
                    {"source": "second_start", "target": "approval"},
                    {"source": "approval", "target": "end"},
                ],
            },
            "multiple_start_nodes",
        ),
        (
            {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "approval", "type": "approval", "approver_id": "u1"},
                ],
                "edges": [{"source": "start", "target": "approval"}],
            },
            "missing_end_node",
        ),
        (
            {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "approval", "type": "approval", "approver_id": "u1"},
                    {"id": "end", "type": "end"},
                    {"id": "second_end", "type": "end"},
                ],
                "edges": [
                    {"source": "start", "target": "approval"},
                    {"source": "approval", "target": "end"},
                ],
            },
            "multiple_end_nodes",
        ),
    ],
)
def test_validator_requires_exactly_one_start_and_end(flow, expected_code):
    assert expected_code in _error_codes(FORM_SCHEMA, flow)


def test_validator_rejects_duplicate_node_ids():
    flow = {
        **FLOW_WITH_AMOUNT_BRANCH,
        "nodes": [
            *FLOW_WITH_AMOUNT_BRANCH["nodes"],
            {
                "id": "manager",
                "type": "approval",
                "approval_type": "single",
                "approver_id": "u1",
            },
        ],
    }

    assert "duplicate_node_id" in _error_codes(FORM_SCHEMA, flow)


def test_validator_rejects_inactive_and_duplicate_countersign_approvers():
    flow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {
                "id": "signers",
                "type": "approval",
                "approval_type": "counter_sign",
                "approver_ids": ["u1", "u1", "inactive"],
            },
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "signers"},
            {"source": "signers", "target": "end"},
        ],
    }

    codes = _error_codes(FORM_SCHEMA, flow)

    assert {"invalid_countersign_approvers", "inactive_approver"} <= codes


def test_validator_rejects_multiple_default_branches():
    flow = {
        **FLOW_WITH_AMOUNT_BRANCH,
        "edges": [
            *FLOW_WITH_AMOUNT_BRANCH["edges"],
            {"source": "amount_gate", "target": "finance", "default": True},
        ],
    }

    assert "multiple_default_branches" in _error_codes(FORM_SCHEMA, flow)


def test_validator_rejects_branching_from_non_condition_nodes():
    flow = {
        **FLOW_WITH_AMOUNT_BRANCH,
        "edges": [
            *FLOW_WITH_AMOUNT_BRANCH["edges"],
            {"source": "manager", "target": "finance"},
        ],
    }

    assert "invalid_non_condition_branch" in _error_codes(FORM_SCHEMA, flow)


def test_default_branch_is_used_when_conditions_do_not_match():
    path = resolve_execution_path({"amount": 1}, FLOW_WITH_AMOUNT_BRANCH)

    assert [node["id"] for node in path] == ["manager", "finance"]


@pytest.mark.parametrize(
    ("actual", "operator", "expected"),
    [("not-a-number", "gte", 100000), (120000, "not-an-operator", 100000)],
)
def test_comparison_mismatch_and_unknown_operator_fall_back_to_default(actual, operator, expected):
    flow = {
        **FLOW_WITH_AMOUNT_BRANCH,
        "edges": [
            {
                **edge,
                "condition": {"field_id": "amount", "operator": operator, "value": expected},
            }
            if edge["source"] == "amount_gate" and edge.get("condition")
            else edge
            for edge in FLOW_WITH_AMOUNT_BRANCH["edges"]
        ],
    }

    path = resolve_execution_path({"amount": actual}, flow)

    assert [node["id"] for node in path] == ["manager", "finance"]


@pytest.mark.parametrize(
    ("form_schema", "flow_schema", "expected_code"),
    [
        ({"fields": [None]}, FLOW_WITH_AMOUNT_BRANCH, "invalid_field_definition"),
        (FORM_SCHEMA, {**FLOW_WITH_AMOUNT_BRANCH, "nodes": [None]}, "invalid_node_definition"),
        (FORM_SCHEMA, {**FLOW_WITH_AMOUNT_BRANCH, "edges": [None]}, "invalid_edge_definition"),
        (
            FORM_SCHEMA,
            {**FLOW_WITH_AMOUNT_BRANCH, "edges": [{"source": [], "target": "end"}]},
            "invalid_edge_definition",
        ),
        (
            FORM_SCHEMA,
            {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {
                        "id": "signers",
                        "type": "approval",
                        "approval_type": "counter_sign",
                        "approver_ids": [["u1"], {"id": "u2"}],
                    },
                    {"id": "end", "type": "end"},
                ],
                "edges": [
                    {"source": "start", "target": "signers"},
                    {"source": "signers", "target": "end"},
                ],
            },
            "invalid_countersign_approvers",
        ),
        (
            FORM_SCHEMA,
            {
                **FLOW_WITH_AMOUNT_BRANCH,
                "edges": [
                    {
                        **edge,
                        "condition": {"field_id": ["amount"], "operator": ["eq"]},
                    }
                    if edge["source"] == "amount_gate" and edge.get("condition")
                    else edge
                    for edge in FLOW_WITH_AMOUNT_BRANCH["edges"]
                ],
            },
            "invalid_condition",
        ),
    ],
)
def test_validator_returns_structured_errors_for_malformed_members(
    form_schema, flow_schema, expected_code
):
    errors = validate_process_definition(form_schema, flow_schema, {"u1", "u2", "u3"})

    assert expected_code in {error.code for error in errors}


@pytest.mark.parametrize(
    "flow_schema",
    [
        {"nodes": [None], "edges": []},
        {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "approval", "type": "approval"},
            ],
            "edges": [{"source": "start", "target": "approval"}],
        },
        {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "approval", "type": "approval"},
            ],
            "edges": [
                {"source": "start", "target": "approval"},
                {"source": "approval", "target": "start"},
            ],
        },
        {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "end", "type": "end"},
            ],
            "edges": [{"source": [], "target": "end"}],
        },
        {
            **FLOW_WITH_AMOUNT_BRANCH,
            "edges": [
                {
                    **edge,
                    "condition": {"field_id": ["amount"], "operator": "eq", "value": 1},
                }
                if edge["source"] == "amount_gate" and edge.get("condition")
                else edge
                for edge in FLOW_WITH_AMOUNT_BRANCH["edges"]
            ],
        },
    ],
)
def test_resolver_raises_value_error_for_malformed_cycle_and_dead_end_graphs(flow_schema):
    with pytest.raises(ValueError):
        resolve_execution_path({}, flow_schema)


@pytest.mark.parametrize(
    ("form_schema", "flow_schema", "expected_code"),
    [
        ({"fields": {}}, FLOW_WITH_AMOUNT_BRANCH, "invalid_fields_section"),
        (FORM_SCHEMA, {**FLOW_WITH_AMOUNT_BRANCH, "nodes": {}}, "invalid_nodes_section"),
        (FORM_SCHEMA, {**FLOW_WITH_AMOUNT_BRANCH, "edges": "not-a-list"}, "invalid_edges_section"),
    ],
)
def test_validator_rejects_non_list_top_level_schema_sections(
    form_schema, flow_schema, expected_code
):
    assert expected_code in _error_codes(form_schema, flow_schema)


def test_validator_rejects_unknown_node_type():
    flow = {
        **FLOW_WITH_AMOUNT_BRANCH,
        "nodes": [
            {**node, "type": "parallel_gateway"} if node["id"] == "manager" else node
            for node in FLOW_WITH_AMOUNT_BRANCH["nodes"]
        ],
    }

    assert "unknown_node_type" in _error_codes(FORM_SCHEMA, flow)


def test_validator_supports_countersign_nodes():
    flow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "signers", "type": "countersign", "approver_ids": ["u1", "u2"]},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "signers"},
            {"source": "signers", "target": "end"},
        ],
    }

    assert _error_codes(FORM_SCHEMA, flow) == set()


def test_resolver_returns_countersign_nodes_as_approval_steps():
    flow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "signers", "type": "countersign", "approver_ids": ["u1", "u2"]},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "signers"},
            {"source": "signers", "target": "end"},
        ],
    }

    assert [node["id"] for node in resolve_execution_path({}, flow)] == ["signers"]


@pytest.mark.parametrize(
    ("condition", "expected_code"),
    [
        ({"field_id": "", "operator": "eq", "value": 1}, "invalid_condition"),
        ({"field_id": "amount", "operator": "between", "value": 1}, "invalid_condition_operator"),
        ({"field_id": "amount", "operator": "eq"}, "missing_condition_value"),
    ],
)
def test_validator_requires_complete_condition_definitions(condition, expected_code):
    flow = {
        **FLOW_WITH_AMOUNT_BRANCH,
        "edges": [
            {**edge, "condition": condition}
            if edge["source"] == "amount_gate" and edge.get("condition")
            else edge
            for edge in FLOW_WITH_AMOUNT_BRANCH["edges"]
        ],
    }

    assert expected_code in _error_codes(FORM_SCHEMA, flow)


def test_validator_accepts_compatibility_expected_condition_value():
    flow = {
        **FLOW_WITH_AMOUNT_BRANCH,
        "edges": [
            {
                **edge,
                "condition": {"field_id": "amount", "operator": "gte", "expected": 100000},
            }
            if edge["source"] == "amount_gate" and edge.get("condition")
            else edge
            for edge in FLOW_WITH_AMOUNT_BRANCH["edges"]
        ],
    }

    assert _error_codes(FORM_SCHEMA, flow) == set()


def test_validator_rejects_end_node_outgoing_edges():
    flow = {
        **FLOW_WITH_AMOUNT_BRANCH,
        "edges": [*FLOW_WITH_AMOUNT_BRANCH["edges"], {"source": "end", "target": "manager"}],
    }

    assert "invalid_end_outgoing" in _error_codes(FORM_SCHEMA, flow)
