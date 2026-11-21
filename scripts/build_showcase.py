"""Build an explicitly curated public example from the pinned UCI dataset, never user workspaces."""

import json

from marketing.analytics import aggregate
from marketing.config import ROOT
from marketing.db import Session
from marketing.delivery import export_html
from marketing.schemas import Query

DATASET = "b3055ee355f59134d851d32641183cb4a8b45def7124d2f50442a042f358e0d9"


def main():
    evidence = []
    with Session() as db:
        for i, dims in enumerate([["traffic_type"], ["visitor_type"], ["traffic_type", "visitor_type"]]):
            query = Query(group_by=dims, filters={"month": ["Nov"]})
            result = aggregate(db, DATASET, query)
            evidence.append({"id": f"sample-e{i + 1}", "query": query.model_dump(), "result": result})
    visitor = {r["visitor_type"]: r for r in evidence[1]["result"]["rows"]}
    new, returning = visitor["New_Visitor"], visitor["Returning_Visitor"]
    claims = [
        {
            "id": "sample-c1",
            "text": f"11 月新访客购买转化率为 {new['conversion_rate']:.2%}（{new['purchases']}/{new['sessions']}），回访者为 {returning['conversion_rate']:.2%}（{returning['purchases']}/{returning['sessions']}）。两组观察到的表现不同。",
            "evidence_ids": ["sample-e2"],
            "limitation": "这是描述性差异，未控制其他因素，不能据此判断访客身份导致转化变化。",
        },
        {
            "id": "sample-c2",
            "text": "继续按流量类型与访客类型交叉分组，检查总体差异是否在各流量分组中一致；样本少于 30 的分组单独提示，不直接用于稳定排序。",
            "evidence_ids": ["sample-e3"],
            "limitation": "此报告未执行显著性检验，也不能评估广告成本或 ROI。",
        },
    ]
    payload = {
        "id": "showcase-november",
        "version": 1,
        "status": "published",
        "delivery_label": "固定公开示例（程序计算，非实时模型输出）",
        "stale_claims": False,
        "spec": {
            "title": "11 月流量转化与访客结构分析",
            "intro_html": "<p>先观察流量表现，再检查新老访客差异，最后回到交叉分组核对证据。</p>",
            "chart": "bar",
            "metric": "conversion_rate",
            "claim_ids": [c["id"] for c in claims],
        },
        "query": evidence[0]["query"],
        "data": evidence[0]["result"],
        "claims": claims,
        "evidence": evidence,
    }
    target = ROOT / "web/public"
    target.mkdir(exist_ok=True)
    (target / "showcase.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (target / "sample-report.html").write_text(export_html(payload), encoding="utf-8")
    print("Public example built from pinned UCI data; no model, user, session or credential data exported.")


if __name__ == "__main__":
    main()
