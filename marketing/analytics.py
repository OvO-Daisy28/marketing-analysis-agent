import hashlib
import json

from sqlalchemy import case, func, select

from marketing.models import Dataset, Evidence, ShoppingSession
from marketing.schemas import Query

METRIC_VERSION = "1.0.0"
METRICS = {
    "sessions": {"label": "会话数", "formula": "COUNT(*)", "unit": "次"},
    "purchases": {"label": "购买会话数", "formula": "SUM(purchased)", "unit": "次"},
    "conversion_rate": {
        "label": "购买转化率",
        "formula": "purchases / sessions",
        "unit": "%",
        "zero_denominator": None,
    },
}
LIMITATIONS = [
    "Revenue 是是否购买，不是销售金额。",
    "流量类型是匿名编码，不能映射到具体广告平台。",
    "数据支持描述性关联，不支持投放因果效果、ROI 或按周分析。",
    "小样本分组的转化率可能不稳定。",
]


def contract():
    return {
        "version": METRIC_VERSION,
        "query_schema": Query.model_json_schema(),
        "metrics": METRICS,
        "limitations": LIMITATIONS,
    }


def latest_dataset(db):
    data = db.scalar(select(Dataset).order_by(Dataset.imported_at.desc()))
    if not data:
        raise ValueError("尚未导入数据，请运行 python -m marketing.cli import-data")
    return data


def aggregate(db, dataset_id, query: Query):
    if not db.get(Dataset, dataset_id):
        raise ValueError("数据版本不存在")
    cols = [getattr(ShoppingSession, d) for d in query.group_by]
    count = func.count(ShoppingSession.id).label("sessions")
    purchases = func.sum(case((ShoppingSession.purchased.is_(True), 1), else_=0)).label("purchases")
    stmt = select(*cols, count, purchases).where(ShoppingSession.dataset_id == dataset_id)
    for key, values in query.filters.model_dump().items():
        if values:
            stmt = stmt.where(getattr(ShoppingSession, key).in_(values))
    if cols:
        stmt = stmt.group_by(*cols).order_by(*cols)
    rows = []
    for raw in db.execute(stmt).mappings():
        row = dict(raw)
        row["purchases"] = row["purchases"] or 0
        row["conversion_rate"] = row["purchases"] / row["sessions"] if row["sessions"] else None
        row["small_sample"] = row["sessions"] < 30
        rows.append(row)
    n, p = sum(r["sessions"] for r in rows), sum(r["purchases"] for r in rows)
    return {
        "rows": rows,
        "totals": {"sessions": n, "purchases": p, "conversion_rate": p / n if n else None},
        "dataset_id": dataset_id,
        "metric_version": METRIC_VERSION,
        "query": query.model_dump(),
        "empty": n == 0,
        "limitations": LIMITATIONS,
    }


def collect_evidence(db, goal, query):
    payload = {"query": query.model_dump(), "dataset_id": goal.dataset_id, "metric_version": METRIC_VERSION}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    previous = db.scalar(select(Evidence).where(Evidence.goal_id == goal.id, Evidence.query_hash == digest))
    if previous:
        return previous
    evidence = Evidence(
        goal_id=goal.id,
        query_hash=digest,
        query=query.model_dump(),
        result=aggregate(db, goal.dataset_id, query),
    )
    db.add(evidence)
    db.flush()
    return evidence
