import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import TicketPriority, TicketStatus


class DashboardSummaryResponse(BaseModel):
    total: int
    pending: int
    in_progress: int
    waiting: int
    completed: int
    cancelled: int
    overdue: int
    average_resolution_hours: float | None


class StatusDistributionItem(BaseModel):
    status: TicketStatus
    count: int


class PriorityDistributionItem(BaseModel):
    priority: TicketPriority
    count: int


class DashboardCategorySummary(BaseModel):
    id: uuid.UUID
    name: str
    model_config = ConfigDict(from_attributes=True)


class DashboardUserSummary(BaseModel):
    id: uuid.UUID
    name: str
    model_config = ConfigDict(from_attributes=True)


class RecentTicketResponse(BaseModel):
    id: uuid.UUID
    title: str
    status: TicketStatus
    priority: TicketPriority
    due_date: datetime | None
    created_at: datetime
    category: DashboardCategorySummary
    assignee: DashboardUserSummary | None


class OverdueTicketResponse(RecentTicketResponse):
    overdue_seconds: int
