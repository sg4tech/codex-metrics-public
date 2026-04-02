from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WorkflowState(str, Enum):
    CLEAN_NO_ACTIVE_GOAL = "clean_no_active_goal"
    STARTED_WORK_WITHOUT_ACTIVE_GOAL = "started_work_without_active_goal"
    ACTIVE_GOAL_EXISTS = "active_goal_exists"
    CLOSED_GOAL_REPAIR = "closed_goal_repair"
    DETECTION_UNCERTAIN = "detection_uncertain"


class WorkflowEvent(str, Enum):
    START_TASK = "start-task"
    CONTINUE_TASK = "continue-task"
    FINISH_TASK_SUCCESS = "finish-task(success)"
    FINISH_TASK_FAIL = "finish-task(fail)"
    UPDATE_CREATE = "update(create)"
    UPDATE_CLOSE = "update(close)"
    UPDATE_REPAIR = "update(repair)"
    ENSURE_ACTIVE_TASK = "ensure-active-task"
    SHOW = "show"


@dataclass(frozen=True)
class WorkflowDecision:
    action: str
    message: str


def classify_workflow_state(
    *,
    active_goal_count: int,
    started_work_detected: bool | None,
    git_available: bool,
) -> WorkflowState:
    if active_goal_count > 0:
        return WorkflowState.ACTIVE_GOAL_EXISTS
    if not git_available or started_work_detected is None:
        return WorkflowState.DETECTION_UNCERTAIN
    if started_work_detected:
        return WorkflowState.STARTED_WORK_WITHOUT_ACTIVE_GOAL
    return WorkflowState.CLEAN_NO_ACTIVE_GOAL


def decide_workflow_transition(state: WorkflowState, event: WorkflowEvent) -> WorkflowDecision:
    if state == WorkflowState.CLOSED_GOAL_REPAIR:
        if event in {
            WorkflowEvent.FINISH_TASK_SUCCESS,
            WorkflowEvent.FINISH_TASK_FAIL,
            WorkflowEvent.UPDATE_CLOSE,
            WorkflowEvent.UPDATE_REPAIR,
            WorkflowEvent.START_TASK,
            WorkflowEvent.CONTINUE_TASK,
        }:
            if event == WorkflowEvent.CONTINUE_TASK:
                return WorkflowDecision(
                    action="block",
                    message="closed-goal repair does not permit continuing active work",
                )
            return WorkflowDecision(action="allow", message="closed-goal repair path remains available")
        if event == WorkflowEvent.ENSURE_ACTIVE_TASK:
            return WorkflowDecision(action="no_op", message="No active task recovery needed.")
        if event == WorkflowEvent.SHOW:
            return WorkflowDecision(action="allow", message="summary only")

    if event == WorkflowEvent.ENSURE_ACTIVE_TASK:
        if state == WorkflowState.STARTED_WORK_WITHOUT_ACTIVE_GOAL:
            return WorkflowDecision(
                action="create_recovery_draft",
                message="Created recovery draft for started work without an active goal.",
            )
        if state == WorkflowState.DETECTION_UNCERTAIN:
            return WorkflowDecision(
                action="no_op",
                message="Cannot detect started work reliably; no active task was created.",
            )
        return WorkflowDecision(action="no_op", message="No active task recovery needed.")

    if event == WorkflowEvent.CONTINUE_TASK and state == WorkflowState.STARTED_WORK_WITHOUT_ACTIVE_GOAL:
        return WorkflowDecision(
            action="block",
            message=(
                "repository work appears to have started without an active goal; "
                "run `codex-metrics ensure-active-task` before continuing active work"
            ),
        )

    if event == WorkflowEvent.SHOW:
        if state == WorkflowState.STARTED_WORK_WITHOUT_ACTIVE_GOAL:
            return WorkflowDecision(
                action="warning",
                message=(
                    "repository work appears to have started without an active goal; "
                    "run `codex-metrics ensure-active-task` to recover bookkeeping"
                ),
            )
        if state == WorkflowState.DETECTION_UNCERTAIN:
            return WorkflowDecision(
                action="warning",
                message="unable to detect started work reliably in this repository",
            )
        return WorkflowDecision(action="allow", message="summary only")

    return WorkflowDecision(action="allow", message="allowed")
