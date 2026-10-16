
from pydantic import BaseModel, Field, model_validator


class SubmitRequest(BaseModel):
    process_app_id: int | None = None
    type_id: int | None = None
    title: str
    form_data: dict
    idempotency_key: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_a_submission_target(self) -> "SubmitRequest":
        if self.process_app_id is None and self.type_id is None:
            raise ValueError("process_app_id is required")
        if self.process_app_id is not None and self.type_id is not None:
            raise ValueError("process_app_id and type_id cannot be used together")
        return self


class ApproveRejectBody(BaseModel):
    comment: str


class TransferBody(BaseModel):
    target_user_id: str


class ResubmitBody(BaseModel):
    form_data: dict
    comment: str | None = None
