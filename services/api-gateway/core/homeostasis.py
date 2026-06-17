"""Gateway homeostasis endpoints (status probe and timer ask_task stub)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["homeostasis"])


class AskTaskBody(BaseModel):
    suggested_objectives: list[str] = Field(default_factory=list)


@router.get("/api/v1/homeostasis/status")
async def homeostasis_status():
    return []


@router.post("/api/v1/homeostasis/ask_task")
async def homeostasis_ask_task(body: AskTaskBody = None):
    return {"ok": True, "trigger": "timer"}
