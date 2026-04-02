from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_metrics.workflow_fsm import (  # noqa: E402
    WorkflowDecision,
    WorkflowEvent,
    WorkflowState,
    classify_workflow_state,
    decide_workflow_transition,
)


@pytest.mark.parametrize(
    ("active_goal_count", "started_work_detected", "git_available", "expected"),
    [
        (1, True, True, WorkflowState.ACTIVE_GOAL_EXISTS),
        (0, True, True, WorkflowState.STARTED_WORK_WITHOUT_ACTIVE_GOAL),
        (0, False, True, WorkflowState.CLEAN_NO_ACTIVE_GOAL),
        (0, None, False, WorkflowState.DETECTION_UNCERTAIN),
    ],
)
def test_classify_workflow_state(
    active_goal_count: int,
    started_work_detected: bool | None,
    git_available: bool,
    expected: WorkflowState,
) -> None:
    assert (
        classify_workflow_state(
            active_goal_count=active_goal_count,
            started_work_detected=started_work_detected,
            git_available=git_available,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("state", "event", "expected_action"),
    [
        (WorkflowState.STARTED_WORK_WITHOUT_ACTIVE_GOAL, WorkflowEvent.CONTINUE_TASK, "block"),
        (WorkflowState.STARTED_WORK_WITHOUT_ACTIVE_GOAL, WorkflowEvent.ENSURE_ACTIVE_TASK, "create_recovery_draft"),
        (WorkflowState.STARTED_WORK_WITHOUT_ACTIVE_GOAL, WorkflowEvent.FINISH_TASK_SUCCESS, "allow"),
        (WorkflowState.STARTED_WORK_WITHOUT_ACTIVE_GOAL, WorkflowEvent.SHOW, "warning"),
        (WorkflowState.CLEAN_NO_ACTIVE_GOAL, WorkflowEvent.ENSURE_ACTIVE_TASK, "no_op"),
        (WorkflowState.CLEAN_NO_ACTIVE_GOAL, WorkflowEvent.SHOW, "allow"),
        (WorkflowState.ACTIVE_GOAL_EXISTS, WorkflowEvent.ENSURE_ACTIVE_TASK, "no_op"),
        (WorkflowState.ACTIVE_GOAL_EXISTS, WorkflowEvent.SHOW, "allow"),
        (WorkflowState.CLOSED_GOAL_REPAIR, WorkflowEvent.CONTINUE_TASK, "block"),
        (WorkflowState.CLOSED_GOAL_REPAIR, WorkflowEvent.ENSURE_ACTIVE_TASK, "no_op"),
        (WorkflowState.CLOSED_GOAL_REPAIR, WorkflowEvent.FINISH_TASK_SUCCESS, "allow"),
        (WorkflowState.CLOSED_GOAL_REPAIR, WorkflowEvent.SHOW, "allow"),
        (WorkflowState.DETECTION_UNCERTAIN, WorkflowEvent.CONTINUE_TASK, "allow"),
        (WorkflowState.DETECTION_UNCERTAIN, WorkflowEvent.SHOW, "warning"),
    ],
)
def test_decide_workflow_transition(
    state: WorkflowState,
    event: WorkflowEvent,
    expected_action: str,
) -> None:
    decision = decide_workflow_transition(state, event)

    assert isinstance(decision, WorkflowDecision)
    assert decision.action == expected_action


def test_decide_workflow_transition_reports_clear_message_for_blocked_continue() -> None:
    decision = decide_workflow_transition(
        WorkflowState.STARTED_WORK_WITHOUT_ACTIVE_GOAL,
        WorkflowEvent.CONTINUE_TASK,
    )

    assert decision.action == "block"
    assert "ensure-active-task" in decision.message


def test_decide_workflow_transition_reports_clear_message_for_closed_goal_repair_block() -> None:
    decision = decide_workflow_transition(
        WorkflowState.CLOSED_GOAL_REPAIR,
        WorkflowEvent.CONTINUE_TASK,
    )

    assert decision.action == "block"
    assert "closed-goal repair" in decision.message
