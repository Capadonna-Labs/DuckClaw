"""Orden y transición de pasos."""

from __future__ import annotations

from duckops.sovereign.domain_labels import WizardStep
from duckops.sovereign.draft import WizardProfile

FULL_STEP_ORDER: tuple[WizardStep, ...] = (
    WizardStep.SOVEREIGNTY_AUDIT,
    WizardStep.CORE_SERVICES,
    WizardStep.IDENTITY_SETUP,
    WizardStep.ORCHESTRATION,
    WizardStep.CONNECTIVITY,
    WizardStep.REVIEW_DEPLOY,
)

# Rápido: reconocimiento + Telegram/túneles + revisión (valores por defecto en borrador).
EXPRESS_STEP_ORDER: tuple[WizardStep, ...] = (
    WizardStep.SOVEREIGNTY_AUDIT,
    WizardStep.CONNECTIVITY,
    WizardStep.REVIEW_DEPLOY,
)

STEP_ORDER = FULL_STEP_ORDER


def step_index(step: WizardStep) -> int:
    return FULL_STEP_ORDER.index(step)


def step_order_for_profile(profile: WizardProfile) -> tuple[WizardStep, ...]:
    if profile == "express":
        return EXPRESS_STEP_ORDER
    return FULL_STEP_ORDER


def next_step_in(order: tuple[WizardStep, ...], step: WizardStep) -> WizardStep | None:
    try:
        i = order.index(step)
    except ValueError:
        return None
    if i + 1 < len(order):
        return order[i + 1]
    return None


def prev_step_in(order: tuple[WizardStep, ...], step: WizardStep) -> WizardStep | None:
    try:
        i = order.index(step)
    except ValueError:
        return None
    if i > 0:
        return order[i - 1]
    return None


def next_step(step: WizardStep) -> WizardStep | None:
    return next_step_in(FULL_STEP_ORDER, step)


def prev_step(step: WizardStep) -> WizardStep | None:
    return prev_step_in(FULL_STEP_ORDER, step)
