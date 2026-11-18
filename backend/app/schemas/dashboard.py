from datetime import date

from pydantic import BaseModel, Field


class LicenseUtilization(BaseModel):
    tool_id: int
    tool_name: str
    product_category: str
    purchased_seats: int = Field(ge=0)
    consumed_seats: int = Field(ge=0)
    utilization_percent: float = Field(ge=0, le=100)


class DashboardOverview(BaseModel):
    period_start: date
    period_end: date
    headcount: int = Field(ge=0)
    active_users: int = Field(ge=0)
    total_prompts: int = Field(ge=0)
    total_meetings: int = Field(ge=0)
    license_utilization: list[LicenseUtilization]
    data_available: bool


class DailyPromptTrend(BaseModel):
    usage_date: date
    tool_id: int
    tool_name: str
    prompts: int = Field(ge=0)


class CopilotPeriodSummary(BaseModel):
    report_refresh_date: date
    prompts: int = Field(ge=0)
    active_users: int = Field(ge=0)


class DashboardTrends(BaseModel):
    period_start: date
    period_end: date
    daily_prompts: list[DailyPromptTrend]
    copilot_d90: CopilotPeriodSummary | None
    source_limitations: list[str] = Field(default_factory=list)


class DepartmentUsage(BaseModel):
    department: str
    headcount: int = Field(ge=0)
    daily_active_users: int = Field(ge=0)
    daily_prompts: int = Field(ge=0)
    copilot_active_users: int = Field(ge=0)
    copilot_prompts: int = Field(ge=0)
    total_prompts: int = Field(ge=0)


class DepartmentBreakdown(BaseModel):
    period_start: date
    period_end: date
    departments: list[DepartmentUsage]


class DashboardTopUser(BaseModel):
    user_id: int
    display_name: str
    department: str
    daily_prompts: int = Field(ge=0)
    copilot_prompts: int = Field(ge=0)
    total_prompts: int = Field(ge=0)
    daily_active_days: int = Field(ge=0)
    copilot_active_days: int = Field(ge=0)
    last_active_date: date | None


class DashboardTopUsers(BaseModel):
    period_start: date
    period_end: date
    limit: int = Field(ge=1, le=50)
    users: list[DashboardTopUser]
