from typing import Literal

from pydantic import Field
from sqlalchemy import select

from marketing import models as m
from marketing.analytics import collect_evidence, contract
from marketing.schemas import Query, ReportSpec, Strict
from marketing.services import DomainError, make_report, scoped_evidence, serialize


class Empty(Strict):
    pass


class ReadEvidence(Strict):
    evidence_id: str
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=50)


class HypothesisInput(Strict):
    text: str = Field(min_length=3, max_length=1500)
    hypothesis_id: str | None = None
    status: Literal["open", "supported", "rejected", "inconclusive"] = "open"
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)


class ClaimInput(Strict):
    text: str = Field(min_length=3, max_length=2000)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)
    limitation: str = Field(min_length=3, max_length=1000)


class DraftInput(Strict):
    evidence_id: str
    spec: ReportSpec


class FinishInput(Strict):
    summary: str = Field(min_length=3, max_length=3000)
    criteria_coverage: list[str] = Field(default_factory=list)


class AskInput(Strict):
    question: str = Field(min_length=3, max_length=1500)


DEFINITIONS = {
    "data_contract": (Empty, "读取可用字段、指标和数据限制。"),
    "query_metrics": (Query, "在当前数据版本执行确定性聚合并保存证据。支持最多两个分组维度。"),
    "read_evidence": (ReadEvidence, "分页精读当前目标的已保存证据。"),
    "update_hypothesis": (HypothesisInput, "提出或更新可检验假设；非 open 状态必须引用证据。"),
    "record_claim": (ClaimInput, "登记有证据引用和适用限制的分析结论。"),
    "draft_report": (DraftInput, "使用受控 HTML 和图表配方生成草稿。不能发布。"),
    "finish": (FinishInput, "申请完成分析，程序验证标准覆盖及必需产物。"),
    "ask_user": (AskInput, "数据或必要信息缺失时等待用户补充。"),
}


class ToolRegistry:
    @property
    def schemas(self):
        return [
            {
                "type": "function",
                "function": {"name": name, "description": desc, "parameters": model.model_json_schema()},
            }
            for name, (model, desc) in DEFINITIONS.items()
        ]

    def schemas_for(self, goal):
        schemas = self.schemas
        if goal.mode == "report":
            schemas = [s for s in schemas if s["function"]["name"] != "update_hypothesis"]
        for schema in schemas:
            if schema["function"]["name"] == "finish":
                schema["function"]["parameters"]["properties"]["criteria_coverage"]["items"] = {
                    "type": "string",
                    "enum": goal.criteria,
                }
        return schemas

    def execute(self, db, goal, run, name, raw, call_id):
        if name not in DEFINITIONS:
            raise DomainError("未知工具")
        if goal.mode == "report" and name == "update_hypothesis":
            raise DomainError("直接报表模式不进行假设研究，请交付所需报表")
        a = DEFINITIONS[name][0].model_validate(raw)
        if name == "data_contract":
            return contract()
        if name == "query_metrics":
            e = collect_evidence(db, goal, a)
            return {
                "evidence_id": e.id,
                "query": e.query,
                "totals": e.result["totals"],
                "rows": e.result["rows"][:30],
                "row_count": len(e.result["rows"]),
                "limitations": e.result["limitations"],
            }
        if name == "read_evidence":
            e = scoped_evidence(db, goal.id, a.evidence_id)
            return {
                "evidence_id": e.id,
                "query": e.query,
                "totals": e.result["totals"],
                "rows": e.result["rows"][a.offset : a.offset + a.limit],
                "row_count": len(e.result["rows"]),
            }
        if name == "update_hypothesis":
            for eid in a.evidence_ids:
                scoped_evidence(db, goal.id, eid)
            if a.status != "open" and not a.evidence_ids:
                raise DomainError("验证假设必须引用证据")
            if a.hypothesis_id:
                h = db.get(m.Hypothesis, a.hypothesis_id)
                if not h or h.goal_id != goal.id:
                    raise DomainError("假设不存在")
            else:
                h = db.scalar(
                    select(m.Hypothesis).where(m.Hypothesis.goal_id == goal.id, m.Hypothesis.text == a.text)
                )
                if not h:
                    h = m.Hypothesis(goal_id=goal.id, text=a.text)
                    db.add(h)
            h.text, h.status, h.evidence_ids = a.text, a.status, a.evidence_ids
            db.flush()
            return serialize(h)
        if name == "record_claim":
            for eid in a.evidence_ids:
                scoped_evidence(db, goal.id, eid)
            claim = db.scalar(select(m.Claim).where(m.Claim.goal_id == goal.id, m.Claim.text == a.text))
            if not claim:
                claim = m.Claim(goal_id=goal.id, **a.model_dump())
                db.add(claim)
                db.flush()
            return serialize(claim)
        if name == "draft_report":
            version = make_report(db, goal, a.spec, a.evidence_id, call_id)
            return {"report_id": version.report_id, "version_id": version.id, "status": version.status}
        if name == "ask_user":
            run.status, run.stop_reason = "waiting_input", a.question
            return {"question": a.question}
        if name == "finish":
            if set(goal.criteria) - set(a.criteria_coverage):
                raise DomainError(
                    "未覆盖完成标准：" + ",".join(set(goal.criteria) - set(a.criteria_coverage))
                )
            if not db.scalar(select(m.Report).where(m.Report.goal_id == goal.id)):
                raise DomainError("缺少报表草稿")
            if goal.mode == "research":
                evidence = list(db.scalars(select(m.Evidence).where(m.Evidence.goal_id == goal.id)))
                hypotheses = list(db.scalars(select(m.Hypothesis).where(m.Hypothesis.goal_id == goal.id)))
                claims = list(db.scalars(select(m.Claim).where(m.Claim.goal_id == goal.id)))
                if (
                    len(evidence) < 2
                    or not hypotheses
                    or any(h.status == "open" for h in hypotheses)
                    or not claims
                ):
                    raise DomainError("研究尚缺多组证据、已检查假设或有依据的结论")
            run.status, run.stop_reason = "completed", a.summary
            return {
                "summary": a.summary,
                "verification": "structural_only; semantic support requires evaluation",
            }
        raise DomainError("未实现的工具")
