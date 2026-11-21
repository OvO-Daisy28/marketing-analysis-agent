import time

import bleach
from sqlalchemy import select

from marketing import models as m
from marketing.analytics import collect_evidence, latest_dataset
from marketing.config import settings
from marketing.schemas import ReportSpec


class DomainError(ValueError):
    pass


def owned_goal(db, goal_id, workspace):
    goal = db.get(m.Goal, goal_id)
    if not goal or goal.workspace_id != workspace:
        raise DomainError("对象不存在或无权访问")
    return goal


def owned_run(db, run_id, workspace):
    run = db.get(m.Run, run_id)
    if not run:
        raise DomainError("对象不存在或无权访问")
    owned_goal(db, run.goal_id, workspace)
    return run


def owned_version(db, version_id, workspace):
    version = db.get(m.ReportVersion, version_id)
    if not version:
        raise DomainError("对象不存在或无权访问")
    report = db.get(m.Report, version.report_id)
    goal = owned_goal(db, report.goal_id, workspace)
    return version, report, goal


def event(db, run, kind, payload):
    db.add(m.Event(run_id=run.id, kind=kind, payload=payload))


def create_goal(db, workspace, body):
    old = db.scalar(
        select(m.Goal).where(m.Goal.workspace_id == workspace, m.Goal.request_key == body.request_key)
    )
    if old:
        if old.objective != body.objective or old.mode != body.mode:
            raise DomainError("幂等键已经用于不同请求")
        return old, db.scalar(select(m.Run).where(m.Run.goal_id == old.id).order_by(m.Run.created_at))
    goal = m.Goal(
        workspace_id=workspace,
        objective=body.objective,
        mode=body.mode,
        request_key=body.request_key,
        dataset_id=latest_dataset(db).id,
        criteria=body.criteria
        or (
            ["分组比较", "假设检查", "证据引用", "分析限制"]
            if body.mode == "research"
            else ["报表草稿", "数据来源"]
        ),
    )
    db.add(goal)
    db.flush()
    return goal, continue_goal(db, goal, body.objective, body.request_key)


def continue_goal(db, goal, instruction, key):
    db.refresh(goal, with_for_update=True)
    previous = db.scalar(select(m.Run).where(m.Run.goal_id == goal.id, m.Run.request_key == key))
    if previous:
        if previous.instruction != instruction:
            raise DomainError("幂等键已经用于不同输入")
        return previous
    if db.scalar(select(m.Run).where(m.Run.goal_id == goal.id, m.Run.status.in_(["running", "queued"]))):
        raise DomainError("当前目标已有执行中的任务")
    run = m.Run(goal_id=goal.id, instruction=instruction, request_key=key, provider_mode=settings.model_mode)
    db.add(run)
    db.flush()
    event(db, run, "queued", {"mode": run.provider_mode, "instruction": instruction})
    return run


def scoped_evidence(db, goal_id, evidence_id):
    evidence = db.get(m.Evidence, evidence_id)
    if not evidence or evidence.goal_id != goal_id:
        raise DomainError("证据不存在或不属于当前目标")
    return evidence


def clean_spec(db, goal_id, spec: ReportSpec):
    clean = bleach.clean(
        spec.intro_html,
        tags=["p", "h2", "h3", "strong", "em", "ul", "ol", "li", "br"],
        attributes={},
        protocols=[],
        strip=True,
    )
    if clean != spec.intro_html:
        raise DomainError("页面仅允许无属性的段落、标题和列表；不允许脚本、链接、事件或样式")
    for cid in spec.claim_ids:
        claim = db.get(m.Claim, cid)
        if not claim or claim.goal_id != goal_id:
            raise DomainError("结论不属于当前目标")
    return spec.model_dump()


def make_report(db, goal, spec, evidence_id, key):
    evidence = scoped_evidence(db, goal.id, evidence_id)
    clean = clean_spec(db, goal.id, spec)
    report = m.Report(goal_id=goal.id)
    db.add(report)
    db.flush()
    version = m.ReportVersion(
        report_id=report.id, version=1, request_key=key, spec=clean, evidence_id=evidence.id
    )
    db.add(version)
    db.flush()
    return version


def revise_report(db, report, goal, body):
    db.refresh(report, with_for_update=True)
    old = db.scalar(
        select(m.ReportVersion).where(
            m.ReportVersion.report_id == report.id, m.ReportVersion.request_key == body.request_key
        )
    )
    if old:
        if old.request_payload is not None and old.request_payload != body.model_dump():
            raise DomainError("幂等键已经用于不同修改请求")
        return old
    latest = db.scalar(
        select(m.ReportVersion)
        .where(m.ReportVersion.report_id == report.id)
        .order_by(m.ReportVersion.version.desc())
    )
    base = db.get(m.ReportVersion, body.base_version_id) if body.base_version_id else latest
    if not base or base.report_id != report.id:
        raise DomainError("修改基准版本不存在或不属于此报告")
    evidence = scoped_evidence(db, goal.id, base.evidence_id)
    changed = body.query is not None and body.query.model_dump() != evidence.query
    if changed:
        evidence = collect_evidence(db, goal, body.query)
    spec = clean_spec(db, goal.id, body.spec)
    if changed:
        spec["claim_ids"] = []
        spec["intro_html"] = "<p>筛选范围已变化，旧分析结论已移除。请续接研究以更新结论。</p>"
    version = m.ReportVersion(
        report_id=report.id,
        version=latest.version + 1,
        request_key=body.request_key,
        request_payload=body.model_dump(),
        spec=spec,
        evidence_id=evidence.id,
        stale_claims=changed or base.stale_claims,
    )
    db.add(version)
    db.flush()
    return version


def publish(db, version):
    db.flush()
    db.refresh(version, with_for_update=True)
    if version.status == "published":
        return version
    evidence = db.get(m.Evidence, version.evidence_id)
    # The immutable evidence snapshot is the exact dataset/query/metric version reviewed by the user.
    version.snapshot = evidence.result
    version.status = "published"
    version.published_at = time.time()
    return version


def serialize(obj):
    return {column.name: getattr(obj, column.name) for column in obj.__table__.columns}


def state(db, goal):
    def rows(model):
        return [serialize(x) for x in db.scalars(select(model).where(model.goal_id == goal.id))]

    return {
        "goal": serialize(goal),
        "hypotheses": rows(m.Hypothesis),
        "evidence": rows(m.Evidence),
        "claims": rows(m.Claim),
        "reports": rows(m.Report),
    }
