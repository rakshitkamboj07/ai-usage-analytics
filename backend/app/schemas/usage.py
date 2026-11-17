from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class UsageFilters(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    tool_id: int | None = Field(default=None, gt=0)
    department_id: int | None = Field(default=None, gt=0)


class UsageDailyRecord(BaseModel):
    usage_date: date
    tool_id: int = Field(gt=0)
    department_id: int | None = Field(default=None, gt=0)
    request_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost: Decimal = Field(ge=0)


class UsageSummary(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    tool_id: int | None = None
    department_id: int | None = None
    request_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost: Decimal = Field(ge=0)
