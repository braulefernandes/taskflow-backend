from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_admin_or_manager
from app.db.session import get_db
from app.schemas.dashboard import (
    DashboardSummaryResponse,
    OverdueTicketResponse,
    PriorityDistributionItem,
    RecentTicketResponse,
    StatusDistributionItem,
)
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard")


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    context: AuthContext = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
) -> DashboardSummaryResponse:
    return DashboardService(db).summary(organization_id=context.organization.id)


@router.get("/status-distribution", response_model=list[StatusDistributionItem])
def dashboard_status_distribution(
    context: AuthContext = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
) -> list[StatusDistributionItem]:
    return DashboardService(db).status_distribution(
        organization_id=context.organization.id
    )


@router.get("/priority-distribution", response_model=list[PriorityDistributionItem])
def dashboard_priority_distribution(
    context: AuthContext = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
) -> list[PriorityDistributionItem]:
    return DashboardService(db).priority_distribution(
        organization_id=context.organization.id
    )


@router.get("/recent", response_model=list[RecentTicketResponse])
def dashboard_recent(
    limit: int = Query(default=5, ge=1, le=50),
    context: AuthContext = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
) -> list[RecentTicketResponse]:
    return DashboardService(db).recent(
        organization_id=context.organization.id, limit=limit
    )


@router.get("/overdue", response_model=list[OverdueTicketResponse])
def dashboard_overdue(
    limit: int = Query(default=5, ge=1, le=50),
    context: AuthContext = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
) -> list[OverdueTicketResponse]:
    return DashboardService(db).overdue(
        organization_id=context.organization.id, limit=limit
    )
