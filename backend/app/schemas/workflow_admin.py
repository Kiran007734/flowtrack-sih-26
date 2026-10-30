from __future__ import annotations

from pydantic import Field

from app.schemas.common import APIModel


class WorkflowStageConfig(APIModel):
    key: str = Field(min_length=2, max_length=96)
    display_name: str = Field(min_length=2, max_length=255)
    ordinal: int = Field(ge=1)
    is_initial: bool = False
    entry_prerequisites: list[str] = []


class WorkflowTransitionConfig(APIModel):
    key: str = Field(min_length=2, max_length=96)
    from_stage_key: str
    to_stage_key: str
    required_permission: str = Field(min_length=2, max_length=128)
    authorized_role_keys: list[str] = []
    prerequisites: dict = {}
    blocking_conditions: dict = {}
    explanation: str = Field(min_length=2, max_length=10000)


class WorkflowVersionCreate(APIModel):
    route_type: str = Field(min_length=2, max_length=96)
    source_reference: str | None = Field(default=None, max_length=512)
    stages: list[WorkflowStageConfig] = Field(min_length=1)
    transitions: list[WorkflowTransitionConfig] = []
