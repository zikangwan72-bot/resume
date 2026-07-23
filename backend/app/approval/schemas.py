from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

FieldType = Literal[
    "text",
    "textarea",
    "number",
    "money",
    "date",
    "date_range",
    "radio",
    "checkbox",
    "select",
    "user",
    "department",
    "attachment",
    "section",
    "detail_table",
]
FIELD_TYPES = frozenset(
    {
        "text",
        "textarea",
        "number",
        "money",
        "date",
        "date_range",
        "radio",
        "checkbox",
        "select",
        "user",
        "department",
        "attachment",
        "section",
        "detail_table",
    }
)
BUSINESS_FIELD_TYPES = FIELD_TYPES - {"section"}
NodeType = Literal["start", "approval", "countersign", "condition", "end"]
ApprovalType = Literal["single", "counter_sign"]
APPROVAL_TYPES = frozenset({"single", "counter_sign"})
ComparisonOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains", "not_contains"]


@dataclass(frozen=True)
class DefinitionError:
    code: str
    message: str
    target_id: str | None = None


class FormFieldDefinition(TypedDict):
    id: str
    type: FieldType
    label: NotRequired[str]


class ConditionDefinition(TypedDict):
    field_id: str
    operator: ComparisonOperator
    value: object


class FlowNodeDefinition(TypedDict):
    id: str
    type: NodeType
    approval_type: NotRequired[ApprovalType]
    approver_id: NotRequired[str]
    approver_ids: NotRequired[list[str]]


class FlowEdgeDefinition(TypedDict):
    source: str
    target: str
    condition: NotRequired[ConditionDefinition]
    default: NotRequired[bool]
