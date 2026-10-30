from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Application,
    ApplicationStageHistory,
    ComplianceObligation,
    EvcVisit,
    ReviewerAssignment,
    ValidityRecord,
)
from app.permissions.access import Principal, require_permission, scoped_institution_ids


def _scoped_apps(session: Session, principal: Principal):
    require_permission(principal, "application.read")
    query = select(Application)
    institutions = scoped_institution_ids(session, principal)
    if institutions is not None:
        query = query.where(Application.institution_id.in_(institutions))
    # A scrutiny-only account sees its current active assignments, not all regional cases.
    if "SCRUTINY_OFFICER" in principal.role_keys and not (
        {"REGIONAL_OFFICER", "REGIONAL_ADMINISTRATOR"} & principal.role_keys
    ):
        assigned = select(ReviewerAssignment.application_id).where(
            ReviewerAssignment.reviewer_id == principal.user.id,
            ReviewerAssignment.status == "ACTIVE",
        )
        query = query.where(Application.id.in_(assigned))
    return query


def dashboard_summary(
    session: Session, *, principal: Principal, now: datetime | None = None
) -> dict:
    now = now or datetime.now(UTC)
    apps = list(session.scalars(_scoped_apps(session, principal)))
    ids = [app.id for app in apps]
    stages: dict[str, int] = {}
    regions: dict[str, int] = {}
    ageing = {"0-7 days": 0, "8-30 days": 0, "31-90 days": 0, "91+ days": 0}
    details = []
    for app in apps:
        last = (
            session.scalar(
                select(func.max(ApplicationStageHistory.created_at)).where(
                    ApplicationStageHistory.application_id == app.id
                )
            )
            or app.updated_at
        )
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        days = max(0, (now - last).days)
        bucket = (
            "0-7 days"
            if days <= 7
            else "8-30 days"
            if days <= 30
            else "31-90 days"
            if days <= 90
            else "91+ days"
        )
        stages[app.current_stage_key] = stages.get(app.current_stage_key, 0) + 1
        regions[str(app.assigned_region_id)] = regions.get(str(app.assigned_region_id), 0) + 1
        ageing[bucket] += 1
        details.append(
            {
                "id": str(app.id),
                "reference_number": app.reference_number,
                "title": app.title,
                "stage": app.current_stage_key,
                "status": app.status,
                "last_action_at": last.isoformat(),
                "ageing_days": days,
            }
        )
    if not ids:
        return {
            "generated_at": now.isoformat(),
            "total_active": 0,
            "by_stage": stages,
            "by_region": regions,
            "ageing": ageing,
            "overdue": 0,
            "unassigned": 0,
            "evc_pending": 0,
            "compliance_open": 0,
            "expiring_documents": 0,
            "cases": [],
        }
    overdue = (
        session.scalar(
            select(func.count(ComplianceObligation.id)).where(
                ComplianceObligation.application_id.in_(ids),
                ComplianceObligation.status.not_in(("VERIFIED", "CLOSED")),
                ComplianceObligation.due_at.is_not(None),
                ComplianceObligation.due_at < now,
            )
        )
        or 0
    )
    compliance_open = (
        session.scalar(
            select(func.count(ComplianceObligation.id)).where(
                ComplianceObligation.application_id.in_(ids),
                ComplianceObligation.status.not_in(("VERIFIED", "CLOSED")),
            )
        )
        or 0
    )
    evc_pending = (
        session.scalar(
            select(func.count(EvcVisit.id)).where(
                EvcVisit.application_id.in_(ids), EvcVisit.status.not_in(("COMPLETED", "CANCELLED"))
            )
        )
        or 0
    )
    unassigned = (
        session.scalar(
            select(func.count(Application.id)).where(
                Application.id.in_(ids),
                Application.current_stage_key == "scrutiny",
                ~Application.id.in_(
                    select(ReviewerAssignment.application_id).where(
                        ReviewerAssignment.status == "ACTIVE"
                    )
                ),
            )
        )
        or 0
    )
    scoped_institutions = [app.institution_id for app in apps]
    expiring = (
        session.scalar(
            select(func.count(ValidityRecord.id)).where(
                ValidityRecord.institution_id.in_(scoped_institutions),
                ValidityRecord.expiry_date.is_not(None),
                ValidityRecord.expiry_date <= now + timedelta(days=30),
                ValidityRecord.renewal_status != "RENEWED",
            )
        )
        or 0
    )
    return {
        "generated_at": now.isoformat(),
        "total_active": len([app for app in apps if app.status != "ROUTE_COMPLETE"]),
        "by_stage": stages,
        "by_region": regions,
        "ageing": ageing,
        "overdue": int(overdue),
        "unassigned": int(unassigned),
        "evc_pending": int(evc_pending),
        "compliance_open": int(compliance_open),
        "expiring_documents": int(expiring),
        "cases": details,
    }
