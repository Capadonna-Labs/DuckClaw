"""DTOs REPORTS_STATE_DELTA (main.custom_reports mutations)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CustomReportMutation(BaseModel):
    report_id: str = Field(..., min_length=1, max_length=100)
    title: str = Field(default="Reporte", max_length=200)
    html_content: str = Field(..., min_length=1)
    created_by: str = Field(default="", max_length=200)


class ReportsStateDelta(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    delta_type: Literal["CUSTOM_REPORT_UPSERT"] = "CUSTOM_REPORT_UPSERT"
    user_id: str = Field(..., min_length=1)
    target_db_path: str = Field(..., min_length=1)
    mutation: CustomReportMutation
