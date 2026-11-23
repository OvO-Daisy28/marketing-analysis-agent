import time

import pytest
from sqlalchemy import func, select

from marketing import models as m
from marketing.analytics import aggregate, collect_evidence
from marketing.config import settings
from marketing.provider import MockProvider, ProviderError
from marketing.schemas import NewGoal, Query, ReportSpec, Revision
from marketing.services import DomainError, create_goal, make_report, publish, revise_report
from marketing.worker import AgentLoop, claim_run, work_once


def new_task(
    factory, mode="research", text="比较流量类型转化表现，并检查访客结构差异", context_mode="structured"
):
    with factory.begin() as db:
        g, r = create_goal(db, "workspace-one", NewGoal(objective=text, mode=mode, request_key=m.uid()))
        r.context_mode = context_mode
        return g.id, r.id


def read(factory, model, id):
    with factory() as db:
        return db.get(model, id)


def test_weighted_rate_and_empty(factory):
    with factory() as db:
        result = aggregate(db, "fixture", Query(group_by=["traffic_type"]))
        assert result["totals"] == {"sessions": 12, "purchases": 4, "conversion_rate": 1 / 3}
        assert sum(r["sessions"] for r in result["rows"]) == 12
        empty = aggregate(db, "fixture", Query(filters={"month": ["Jan"]}))
        assert empty["empty"] and empty["totals"]["conversion_rate"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"roi": True},
        {"group_by": ["spend"]},
        {"filters": {"week": ["this"]}},
        {"group_by": ["month", "month"]},
    ],
)
def test_query_rejects_unknown_contract(body):
    with pytest.raises(ValueError):
        Query.model_validate(body)


@pytest.mark.parametrize("mode", ["report", "research"])
def test_mock_full_lifecycle(factory, mode):
    gid, rid = new_task(factory, mode)
    assert work_once(factory)
    run = read(factory, m.Run, rid)
    assert run.status == "completed", run.stop_reason
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.Report).where(m.Report.goal_id == gid)) == 1
        assert db.scalar(select(func.count()).select_from(m.Evidence).where(m.Evidence.goal_id == gid)) == (
            2 if mode == "research" else 1
        )
    assert not work_once(factory)


def test_report_revision_snapshot_and_publish_idempotent(factory):
    gid, rid = new_task(factory, "report")
    work_once(factory)
    with factory.begin() as db:
        report = db.scalar(select(m.Report).where(m.Report.goal_id == gid))
        first = db.scalar(select(m.ReportVersion).where(m.ReportVersion.report_id == report.id))
        publish(db, first)
        timestamp = first.published_at
        publish(db, first)
        assert first.published_at == timestamp
        spec = ReportSpec.model_validate(first.spec)
        spec.title = "新标题"
        style = revise_report(db, report, db.get(m.Goal, gid), Revision(spec=spec, request_key="style-only"))
        assert style.evidence_id == first.evidence_id and not style.stale_claims
        filtered = revise_report(
            db,
            report,
            db.get(m.Goal, gid),
            Revision(spec=spec, query=Query(filters={"month": ["Dec"]}), request_key="new-range"),
        )
        assert filtered.stale_claims and filtered.spec["claim_ids"] == []
        assert db.get(m.Evidence, filtered.evidence_id).result["totals"]["sessions"] == 4
        with pytest.raises(DomainError, match="旧结论已失效"):
            publish(db, filtered)
        assert first.snapshot["totals"]["sessions"] == 12
        again = revise_report(
            db,
            report,
            db.get(m.Goal, gid),
            Revision(spec=spec, query=Query(filters={"month": ["Dec"]}), request_key="new-range"),
        )
        assert again.id == filtered.id
        with pytest.raises(DomainError):
            revise_report(
                db,
                report,
                db.get(m.Goal, gid),
                Revision(spec=ReportSpec(title="different payload"), request_key="new-range"),
            )
        from_original = revise_report(
            db,
            report,
            db.get(m.Goal, gid),
            Revision(
                base_version_id=first.id,
                spec=ReportSpec(title="从最初版本改标题"),
                request_key="old-base-edit",
            ),
        )
        assert from_original.evidence_id == first.evidence_id
        assert not from_original.stale_claims


@pytest.mark.parametrize(
    "html",
    [
        "<script>alert(1)</script>",
        '<p onclick="alert(1)">x</p>',
        '<img src="https://evil.invalid">',
        "<iframe></iframe>",
    ],
)
def test_unsafe_html_rejected(factory, html):
    gid, _ = new_task(factory)
    with factory.begin() as db:
        goal = db.get(m.Goal, gid)
        e = collect_evidence(db, goal, Query())
        with pytest.raises(DomainError):
            make_report(db, goal, ReportSpec(title="test", intro_html=html), e.id, "x")


def test_cross_goal_evidence_rejected(factory):
    a, _ = new_task(factory)
    b, _ = new_task(factory)
    with factory.begin() as db:
        e = collect_evidence(db, db.get(m.Goal, a), Query())
        with pytest.raises(DomainError):
            make_report(db, db.get(m.Goal, b), ReportSpec(title="test"), e.id, "x")


def test_api_csrf_isolation_and_no_implicit_publish(logged, factory):
    body = {"objective": "生成转化率报告", "mode": "report", "request_key": "test-request-1"}
    a = logged.post("/api/goals", json=body)
    assert a.status_code == 201
    b = logged.post("/api/goals", json=body)
    assert b.json()["goal"]["id"] == a.json()["goal"]["id"]
    work_once(factory)
    report = logged.get("/api/reports").json()[0]
    assert report["versions"][0]["status"] == "draft"
    logged.headers.pop("X-CSRF-Token")
    assert (
        logged.post("/api/report-versions/" + report["versions"][0]["id"] + "/publish", json={}).status_code
        == 403
    )
    other = {"username": "another", "password": "another-password"}
    logged.post("/api/auth/register", json=other)
    response = logged.post("/api/auth/login", json=other)
    logged.headers["X-CSRF-Token"] = response.json()["csrf"]
    assert logged.get("/api/reports").json() == []
    assert logged.get("/api/goals/" + a.json()["goal"]["id"]).status_code == 400
    assert logged.get("/api/report-versions/" + report["versions"][0]["id"]).status_code == 400


def test_api_blocks_stale_publication_after_style_revision(logged, factory):
    created = logged.post(
        "/api/goals",
        json={"objective": "生成转化率报告", "mode": "report", "request_key": "stale-api"},
    ).json()
    work_once(factory)
    with factory.begin() as db:
        goal = db.get(m.Goal, created["goal"]["id"])
        report = db.scalar(select(m.Report).where(m.Report.goal_id == goal.id))
        changed = revise_report(
            db,
            report,
            goal,
            Revision(
                spec=ReportSpec(title="改月份"),
                query=Query(filters={"month": ["Dec"]}),
                request_key="range-api",
            ),
        )
        styled = revise_report(
            db,
            report,
            goal,
            Revision(base_version_id=changed.id, spec=ReportSpec(title="再改标题"), request_key="style-api"),
        )
        ids = [changed.id, styled.id]
    for vid in ids:
        response = logged.post(f"/api/report-versions/{vid}/publish", json={})
        assert response.status_code == 400
        assert "旧结论已失效" in response.text
        with factory() as db:
            version = db.get(m.ReportVersion, vid)
            assert version.status == "draft" and version.published_at is None


def test_sse_replay_and_cancel(logged, factory):
    r = logged.post("/api/goals", json={"objective": "生成转化率报告", "request_key": "events-test-1"}).json()
    rid = r["run"]["id"]
    # GET subscriptions must never claim or start a task.
    assert logged.get(f"/api/runs/{rid}/events").status_code == 200
    assert read(factory, m.Run, rid).status == "queued"
    logged.post(f"/api/runs/{rid}/cancel", json={})
    response = logged.get(f"/api/runs/{rid}/stream", headers={"Last-Event-ID": "0"})
    assert "event: done" in response.text and "cancelled" in response.text
    ids = [int(x[4:]) for x in response.text.splitlines() if x.startswith("id: ")]
    replay = logged.get(f"/api/runs/{rid}/stream", headers={"Last-Event-ID": str(max(ids))})
    assert "event: progress" not in replay.text


class RepeatingProvider:
    def chat(self, *args):
        return {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "repeat",
                        "type": "function",
                        "function": {"name": "data_contract", "arguments": "{}"},
                    }
                ],
            },
            "usage": {},
        }


def test_no_progress_and_budget(factory, monkeypatch):
    _, rid = new_task(factory)
    work_once(factory, RepeatingProvider())
    assert read(factory, m.Run, rid).stop_reason == "NO_PROGRESS"
    _, rid = new_task(factory)
    monkeypatch.setattr(settings, "max_run_tokens", 10)
    work_once(factory)
    assert read(factory, m.Run, rid).stop_reason == "TOKEN_BUDGET"


def test_lease_recovery_and_fencing(factory):
    _, rid = new_task(factory)
    claimed = claim_run(factory)
    assert claim_run(factory) is None
    with factory.begin() as db:
        run = db.get(m.Run, rid)
        run.lease_until = time.time() - 1
    recovered = claim_run(factory)
    assert recovered[1] != claimed[1]
    AgentLoop(factory).process(*claimed)
    assert read(factory, m.Run, rid).status == "running"
    AgentLoop(factory).process(*recovered)
    assert read(factory, m.Run, rid).status == "completed"


def test_checkpoint_replay_no_duplicate_evidence(factory):
    gid, rid = new_task(factory, "report")
    assert claim_run(factory)
    with factory.begin() as db:
        run = db.get(m.Run, rid)
        run.steps = 1
        run.pending = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "durable",
                        "type": "function",
                        "function": {"name": "query_metrics", "arguments": "{}"},
                    }
                ],
            },
            "next": 0,
            "before": "before",
        }
        run.lease_until = time.time() - 1
    recovered = claim_run(factory)
    AgentLoop(factory).process(*recovered)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.Evidence).where(m.Evidence.goal_id == gid)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.ToolExecution)
                .where(m.ToolExecution.run_id == rid, m.ToolExecution.call_id == "1:durable")
            )
            == 1
        )


def test_retry_and_unsupported_request(factory, monkeypatch):
    import marketing.worker as worker

    monkeypatch.setattr(worker.time, "sleep", lambda x: None)

    class Flaky(MockProvider):
        n = 0

        def chat(self, *args):
            self.n += 1
            if self.n == 1:
                raise ProviderError("MODEL_HTTP_429", True)
            return super().chat(*args)

    _, rid = new_task(factory, "report")
    work_once(factory, Flaky())
    assert read(factory, m.Run, rid).status == "completed"
    _, rid = new_task(factory, "research", "计算广告成本和ROI")
    work_once(factory)
    assert read(factory, m.Run, rid).status == "waiting_input"


def test_context_pairs_and_live_provider_protocol(factory, monkeypatch):
    from marketing.context import ContextBuilder
    from marketing.tools import ToolRegistry

    gid, rid = new_task(factory)
    work_once(factory)
    with factory() as db:
        messages, _ = ContextBuilder().build(
            db, db.get(m.Goal, gid), db.get(m.Run, rid), ToolRegistry().schemas
        )
    calls = {c["id"] for x in messages for c in x.get("tool_calls", [])}
    returned = {x["tool_call_id"] for x in messages if x["role"] == "tool"}
    assert calls == returned


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("{}{}", "{}"),
        ('{}{"group_by":[]}', '{"group_by":[]}'),
        ('{"a":1}{"b":2}', '{"a":1}{"b":2}'),
        ("{}{}{}", "{}{}{}"),
    ],
)
def test_provider_compatibility_is_narrow(monkeypatch, raw, expected):
    import httpx

    from marketing.provider import LiveProvider

    monkeypatch.setattr(settings, "llm_api_key", "test-only")
    monkeypatch.setattr(settings, "llm_model", "fixture")
    monkeypatch.setattr(settings, "tool_arguments_empty_prefix_fix", True)
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **kw: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {"id": "t", "function": {"name": "query_metrics", "arguments": raw}}
                            ]
                        }
                    }
                ]
            },
        ),
    )
    result = LiveProvider().chat([], [], {})
    assert result["message"]["tool_calls"][0]["function"]["arguments"] == expected
