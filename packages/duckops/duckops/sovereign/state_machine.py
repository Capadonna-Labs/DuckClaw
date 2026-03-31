"""Orden y transición de pasos."""

from __future__ import annotations

from duckops.sovereign.domain_labels import WizardStep

STEP_ORDER: tuple[WizardStep, ...] = (
    WizardStep.SOVEREIGNTY_AUDIT,
    WizardStep.CORE_SERVICES,
    WizardStep.IDENTITY_SETUP,
    WizardStep.CONNECTIVITY,
    WizardStep.ORCHESTRATION,
    WizardStep.REVIEW_DEPLOY,
)


def step_index(step: WizardStep) -> int:
    return STEP_ORDER.index(step)


def next_step(step: WizardStep) -> WizardStep | None:
    i = step_index(step)
    if i + 1 < len(STEP_ORDER):
        return STEP_ORDER[i + 1]
    return None


def prev_step(step: WizardStep) -> WizardStep | None:
    i = step_index(step)
    if i > 0:
        return STEP_ORDER[i - 1]
    return None
