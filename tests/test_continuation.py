import json

import pytest
from sqlalchemy import select

from marketing import models as m
from marketing.schemas import NewGoal
from marketing.services import DomainError, continue_goal, create_goal
from marketing.worker import work_once


def initial_report(factory):
    with factory.begin() as db:
        goal, _ = create_goal(db, "audit", NewGoal(objective="生成转化率报表", request_key="audit-create"))
        gid = goal.id
    work_once(factory)
    with factory.begin() as db:
        run = continue_goal(db, db.get(m.Goal, gid), "重新整理这份报告", "audit-continue")
        return gid, run.id


def test_followup_cannot_finish_using_only_previous_report(factory):
    _, rid = initial_report(factory)

    class SkipDelivery:
        def chat(self, messages, tools, context):
            return {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "premature",
                            "type": "function",
                            "function": {
                                "name": "finish",
                                "arguments": json.dumps(
                                    {
                                        "summary": "沿用原来的报告",
                                        "criteria_coverage": context["goal"]["criteria"],
                                    }
                                ),
                            },
                        }
                    ],
                },
                "usage": {},
            }

    work_once(factory, SkipDelivery())
    with factory() as db:
        run = db.get(m.Run, rid)
        assert run.status == "stopped" and run.stop_reason == "NO_PROGRESS"
        attempts = list(db.scalars(select(m.ToolExecution).where(m.ToolExecution.run_id == rid)))
        assert attempts and all(not t.result["ok"] for t in attempts)
        assert "当前轮次" in attempts[0].result["error"]["message"]


def test_mock_continuation_delivers_new_draft(factory):
    gid, rid = initial_report(factory)
    work_once(factory)
    with factory() as db:
        assert db.get(m.Run, rid).status == "completed"
        assert len(list(db.scalars(select(m.Report).where(m.Report.goal_id == gid)))) == 2


def test_goal_idempotency_includes_completion_criteria(factory):
    with factory.begin() as db:
        body = NewGoal(objective="生成转化率报表", request_key="same-request")
        goal, run = create_goal(db, "audit", body)
        same, same_run = create_goal(db, "audit", body)
        assert (same.id, same_run.id) == (goal.id, run.id)
        with pytest.raises(DomainError, match="幂等键"):
            create_goal(db, "audit", body.model_copy(update={"criteria": ["新增检验标准"]}))
