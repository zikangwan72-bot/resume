from dataclasses import dataclass
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, Field

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


class ProcessAppCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    category: Annotated[str, Field(min_length=1, max_length=80)] = "通用审批"
    description: str | None = None
    form_schema: dict[str, Any]
    flow_schema: dict[str, Any]


class ProcessAppUpdate(BaseModel):
    code: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    category: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    description: str | None = None
    form_schema: dict[str, Any] | None = None
    flow_schema: dict[str, Any] | None = None


class ApprovalUserCreate(BaseModel):
    display_name: Annotated[str, Field(min_length=1, max_length=100)]
    email: Annotated[str, Field(min_length=3, max_length=255)]
    department: Annotated[str, Field(min_length=1, max_length=100)]
    position: Annotated[str, Field(min_length=1, max_length=100)]
    role: Annotated[str, Field(min_length=1, max_length=50)]
    is_active: bool = True


class ApprovalUserUpdate(BaseModel):
    position: Annotated[str, Field(min_length=1, max_length=100)]
    display_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    email: Annotated[str, Field(min_length=3, max_length=255)] | None = None
    department: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    role: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    is_active: bool | None = None
