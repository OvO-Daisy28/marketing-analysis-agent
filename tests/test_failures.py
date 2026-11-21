import json
import time

import pytest
from sqlalchemy import select

from marketing import models as m
from marketing.config import settings
from marketing.provider import ProviderError
from marketing.schemas import NewGoal
from marketing.services import create_goal
from marketing.worker import AgentLoop, claim_run, work_once


def setup_run(factory):
    with factory.begin() as db:
        _, run = create_goal(
            db,
            "fault-workspace",
            NewGoal(objective="分析购买转化并交付报告", mode="research", request_key=m.uid()),
        )
        return run.id


def outcome(factory, id):
    with factory() as db:
        return db.get(m.Run, id)


@pytest.mark.parametrize(
    "code,retryable,expected_calls",
    [("MODEL_HTTP_401", False, 1), ("MODEL_HTTP_429", True, 3), ("MODEL_NETWORK_TIMEOUT", True, 3)],
)
def test_provider_failure_is_bounded(factory, monkeypatch, code, retryable, expected_calls):
    from marketing import worker

    monkeypatch.setattr(worker.time, "sleep", lambda _: None)

    class Failing:
        calls = 0

        def chat(self, *args):
            self.calls += 1
            raise ProviderError(code, retryable)

    provider = Failing()
    rid = setup_run(factory)
    work_once(factory, provider)
    assert provider.calls == expected_calls
    run = outcome(factory, rid)
    assert run.status == "failed" and run.stop_reason == code
    assert run.input_tokens > 0 and run.output_tokens > 0


def test_expired_runtime_stops_before_model(factory):
    rid = setup_run(factory)
    claim = claim_run(factory)
    with factory.begin() as db:
        db.get(m.Run, rid).started_at = time.time() - settings.max_run_seconds - 1
    AgentLoop(factory).process(*claim)
    assert outcome(factory, rid).stop_reason == "TIME_BUDGET"


def test_cancel_during_model_call_discards_result(factory):
    rid = setup_run(factory)

    class Cancelling:
        def chat(self, *args):
            with factory.begin() as db:
                db.get(m.Run, rid).status = "cancelled"
            return {"message": {"role": "assistant", "content": "ignored"}, "usage": {}}

    work_once(factory, Cancelling())
    run = outcome(factory, rid)
    assert run.status == "cancelled" and run.pending is None and run.messages == []


def test_finish_cannot_bypass_artifact_gate(factory):
    rid = setup_run(factory)

    class Premature:
        def chat(self, messages, tools, context):
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "same",
                            "type": "function",
                            "function": {
                                "name": "finish",
                                "arguments": json.dumps(
                                    {
                                        "summary": "已经完成分析",
                                        "criteria_coverage": context["goal"]["criteria"],
                                    }
                                ),
                            },
                        }
                    ],
                },
                "usage": {},
            }

    work_once(factory, Premature())
    run = outcome(factory, rid)
    assert run.status == "stopped"
    with factory() as db:
        executions = list(db.scalars(select(m.ToolExecution).where(m.ToolExecution.run_id == rid)))
        assert all(not t.result["ok"] for t in executions)


def test_unknown_tool_is_rejected(factory):
    rid = setup_run(factory)

    class Unknown:
        def chat(self, *args):
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "bad",
                            "type": "function",
                            "function": {"name": "publish_report", "arguments": "{}"},
                        }
                    ],
                },
                "usage": {},
            }

    work_once(factory, Unknown())
    assert outcome(factory, rid).status == "stopped"
