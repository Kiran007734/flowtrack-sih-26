from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class CommitteeCreate(APIModel):
    stage_key: str = Field(min_length=1, max_length=96)
    committee_type: str = Field(min_length=2, max_length=64)


class CommitteeMemberCreate(APIModel):
    user_id: UUID


class CommitteeSubmissionCreate(APIModel):
    recommendation: str = Field(pattern="^(RECOMMEND_APPROVAL|RECOMMEND_REJECTION|RETURN|DEFER)$")
    findings: str = Field(min_length=5, max_length=10000)


class CommitteeFinalize(APIModel):
    outcome: str = Field(pattern="^(RECOMMEND_APPROVAL|RECOMMEND_REJECTION|RETURN|DEFER)$")
    reason: str = Field(min_length=5, max_length=10000)
