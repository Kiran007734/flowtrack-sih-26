from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Application,
    Deficiency,
    Document,
    EvcChecklistItem,
    EvcEvidenceLink,
    EvcReport,
    EvcVisit,
    WorkflowTransition,
)
from app.permissions.access import Principal, require_institution_access


@dataclass(frozen=True)
class TransitionEvaluation:
    transition_key: str
    allowed: bool
    reason_code: str
    explanation: str
    missing_prerequisites: list[str]
    required_permission: str | None
    applicable_workflow_version: UUID
    to_stage_key: str | None


def _fact_failure(
    session: Session, application: Application, fact: str, definition: dict[str, Any]
) -> str | None:
    if fact == "application.required_fields":
        missing = [
            field
            for field, value in {
                "title": application.title,
                "application_type": application.application_type,
            }.items()
            if not value or not str(value).strip()
        ]
        return f"Complete required application fields: {', '.join(missing)}" if missing else None
    if fact == "documents.minimum_count":
        minimum = int(definition.get("minimum", definition.get("minimum_documents", 1)))
        count = int(
            session.scalar(
                select(func.count(Document.id)).where(
                    Document.application_id == application.id,
                    Document.status == "AVAILABLE",
                )
            )
            or 0
        )
        if count < minimum:
            return f"Upload at least {minimum} available document(s) before this transition"
        return None
    if fact == "deficiencies.all_responded":
        open_count = int(
            session.scalar(
                select(func.count(Deficiency.id)).where(
                    Deficiency.application_id == application.id,
                    Deficiency.status.not_in(("RESPONDED", "RESOLVED")),
                )
            )
            or 0
        )
        if open_count:
            return "Respond to every open deficiency before resubmitting"
        return None
    if fact in {
        "evc.visit.completed",
        "evc.report.accepted",
        "evc.checklist.completed",
        "evc.evidence.linked",
        "evc.evidence.verified",
        "evc.human_review.completed",
    }:
        visit = session.scalar(select(EvcVisit).where(EvcVisit.application_id == application.id))
        if visit is None:
            return "A configured EVC visit is required"
        if fact == "evc.visit.completed" and visit.status != "COMPLETED":
            return "Complete the configured EVC visit"
        if fact == "evc.report.accepted" and not session.scalar(
            select(EvcReport.id).where(
                EvcReport.visit_id == visit.id, EvcReport.status.in_(("ACCEPTED", "CLOSED"))
            )
        ):
            return "An accepted EVC report is required"
        if fact == "evc.human_review.completed" and not session.scalar(
            select(EvcReport.id).where(
                EvcReport.visit_id == visit.id, EvcReport.status.in_(("ACCEPTED", "CLOSED"))
            )
        ):
            return "A configured EVC human review is required"
        if fact == "evc.checklist.completed":
            labels = definition.get("labels", [])
            query = select(EvcChecklistItem.id).where(
                EvcChecklistItem.visit_id == visit.id,
                EvcChecklistItem.status == "COMPLETED",
            )
            if labels:
                query = query.where(EvcChecklistItem.label.in_(labels))
                if len(list(session.scalars(query))) != len(set(labels)):
                    return "Complete every configured EVC checklist item"
            elif not session.scalar(query):
                return "Complete the configured EVC checklist items"
        if fact in {"evc.evidence.linked", "evc.evidence.verified"}:
            query = select(EvcEvidenceLink.purpose).where(EvcEvidenceLink.visit_id == visit.id)
            if fact == "evc.evidence.verified":
                query = query.where(EvcEvidenceLink.status == "VERIFIED")
            else:
                query = query.where(EvcEvidenceLink.status.in_(("LINKED", "VERIFIED")))
            purposes = definition.get("purposes", [])
            available = set(session.scalars(query))
            if purposes and not set(purposes).issubset(available):
                state = "verified" if fact.endswith("verified") else "linked"
                return f"Provide every configured {state} EVC evidence item"
            if not purposes and not available:
                return (
                    "Verified EVC evidence is required"
                    if fact.endswith("verified")
                    else "Linked EVC evidence is required"
                )
        return None
    return f"Unsupported configured prerequisite fact: {fact}"


def _evaluate_expression(session: Session, application: Application, expression: Any) -> list[str]:
    if not expression:
        return []
    if isinstance(expression, str):
        return [failure] if (failure := _fact_failure(session, application, expression, {})) else []
    if isinstance(expression, list):
        failures: list[str] = []
        for item in expression:
            failures.extend(_evaluate_expression(session, application, item))
        return failures
    if not isinstance(expression, dict):
        return ["Invalid workflow prerequisite configuration"]
    if "fact" in expression:
        failure = _fact_failure(session, application, str(expression["fact"]), expression)
        return [failure] if failure else []
    if "all" in expression:
        return _evaluate_expression(session, application, expression["all"])
    if "any" in expression:
        alternatives = [
            _evaluate_expression(session, application, item) for item in expression["any"]
        ]
        if any(not failures for failures in alternatives):
            return []
        flattened = [failure for failures in alternatives for failure in failures]
        return ["At least one configured prerequisite path must be satisfied", *flattened]
    if "not" in expression:
        nested_failures = _evaluate_expression(session, application, expression["not"])
        return ["A configured blocking condition is currently true"] if not nested_failures else []
    if "facts" in expression:
        failures = []
        for fact in expression["facts"]:
            failure = _fact_failure(session, application, str(fact), expression)
            if failure:
                failures.append(failure)
        return failures
    return ["Invalid workflow prerequisite configuration"]


def evaluate_transition(
    session: Session,
    *,
    application: Application,
    principal: Principal,
    transition_key: str,
) -> TransitionEvaluation:
    require_institution_access(principal, application.institution)
    transition = session.scalar(
        select(WorkflowTransition).where(
            WorkflowTransition.template_version_id == application.workflow_template_version_id,
            WorkflowTransition.key == transition_key,
        )
    )
    if transition is None:
        return TransitionEvaluation(
            transition_key=transition_key,
            allowed=False,
            reason_code="transition_not_configured",
            explanation="This transition is not configured for the application's workflow version.",
            missing_prerequisites=[],
            required_permission=None,
            applicable_workflow_version=application.workflow_template_version_id,
            to_stage_key=None,
        )
    if application.current_stage_key != transition.from_stage_key:
        return TransitionEvaluation(
            transition_key=transition_key,
            allowed=False,
            reason_code="invalid_current_stage",
            explanation=(
                "The application is not currently at the stage required for this transition."
            ),
            missing_prerequisites=[],
            required_permission=transition.required_permission,
            applicable_workflow_version=application.workflow_template_version_id,
            to_stage_key=transition.to_stage_key,
        )
    if transition.required_permission not in principal.permissions:
        return TransitionEvaluation(
            transition_key=transition_key,
            allowed=False,
            reason_code="missing_permission",
            explanation=(
                "Your current role grant does not include the permission required for this "
                "transition."
            ),
            missing_prerequisites=[],
            required_permission=transition.required_permission,
            applicable_workflow_version=application.workflow_template_version_id,
            to_stage_key=transition.to_stage_key,
        )
    if transition.authorized_role_keys and not (
        set(transition.authorized_role_keys) & set(principal.role_keys)
    ):
        return TransitionEvaluation(
            transition_key=transition_key,
            allowed=False,
            reason_code="role_not_authorized",
            explanation="Your role is not authorized by this versioned workflow transition.",
            missing_prerequisites=[],
            required_permission=transition.required_permission,
            applicable_workflow_version=application.workflow_template_version_id,
            to_stage_key=transition.to_stage_key,
        )
    missing = _evaluate_expression(session, application, transition.prerequisites)
    if missing:
        return TransitionEvaluation(
            transition_key=transition_key,
            allowed=False,
            reason_code="prerequisites_unmet",
            explanation="Required evidence or fields are incomplete.",
            missing_prerequisites=missing,
            required_permission=transition.required_permission,
            applicable_workflow_version=application.workflow_template_version_id,
            to_stage_key=transition.to_stage_key,
        )
    return TransitionEvaluation(
        transition_key=transition_key,
        allowed=True,
        reason_code="allowed",
        explanation=transition.explanation,
        missing_prerequisites=[],
        required_permission=transition.required_permission,
        applicable_workflow_version=application.workflow_template_version_id,
        to_stage_key=transition.to_stage_key,
    )
