"""Freeze an inspectable, versioned task suite; never generates success results."""

import json
from itertools import combinations

from marketing.config import ROOT

DIMENSIONS = {
    "traffic_type": "流量类型",
    "visitor_type": "访客类型",
    "month": "月份",
    "region": "地区编码",
    "weekend": "是否周末",
}


def generate():
    cases = []
    for dim, label in DIMENSIONS.items():
        for month, phrase in [(None, "全部样本"), ("Nov", "11月"), ("Dec", "12月"), ("May", "5月")]:
            cases.append(
                {
                    "id": f"report-{len(cases) + 1:02}",
                    "category": "report",
                    "mode": "report",
                    "objective": f"生成{phrase}按{label}分组的购买转化率报表，保留会话数并注明限制。",
                    "expected_dimensions": [dim],
                    "expected_filters": {"month": [month]} if month else {},
                    "expected_status": "completed",
                }
            )
    for a, b in combinations(DIMENSIONS, 2):
        for month, phrase in [(None, "全部样本"), ("Nov", "11月")]:
            cases.append(
                {
                    "id": f"research-{len(cases) - 19:02}",
                    "category": "research",
                    "mode": "research",
                    "objective": f"分析{phrase}的{DIMENSIONS[a]}与{DIMENSIONS[b]}分组转化差异，使用联合分组检验一个假设，记录证据和限制并生成报告。",
                    "expected_dimensions": [a, b],
                    "expected_filters": {"month": [month]} if month else {},
                    "expected_status": "completed",
                }
            )
    for kind in ["title", "chart", "filter", "publish_twice", "history"]:
        cases.append(
            {
                "id": "revision-" + kind,
                "category": "revision",
                "scenario": kind,
                "test": "test_report_revision_snapshot_and_publish_idempotent",
            }
        )
    for kind, test in [
        ("retry", "test_retry_and_unsupported_request"),
        ("lease", "test_lease_recovery_and_fencing"),
        ("pending", "test_checkpoint_replay_no_duplicate_evidence"),
        ("no_progress", "test_no_progress_and_budget"),
        ("token_budget", "test_no_progress_and_budget"),
        ("cancel", "test_sse_replay_and_cancel"),
        ("sse_replay", "test_sse_replay_and_cancel"),
        ("empty_data", "test_weighted_rate_and_empty"),
        ("invalid_parameter", "test_query_rejects_unknown_contract"),
        ("gateway_arguments", "test_provider_compatibility_is_narrow"),
    ]:
        cases.append({"id": "resilience-" + kind, "category": "resilience", "scenario": kind, "test": test})
    for objective in [
        "计算广告成本与ROI，并给出投放优化报告",
        "生成本周每天的销售收入金额趋势",
        "指出哪个广告平台导致购买提升，并证明因果关系",
    ]:
        cases.append(
            {
                "id": f"boundary-{len(cases) - 54}",
                "category": "boundary",
                "mode": "research",
                "objective": objective,
                "expected_status": "waiting_input",
            }
        )
    cases.extend(
        [
            {
                "id": "boundary-isolation",
                "category": "boundary",
                "test": "test_api_csrf_isolation_and_no_implicit_publish",
            },
            {"id": "boundary-html", "category": "boundary", "test": "test_unsafe_html_rejected"},
        ]
    )
    directory = ROOT / "eval"
    directory.mkdir(exist_ok=True)
    (directory / "frozen.json").write_text(
        json.dumps({"version": "1.0.0", "cases": cases}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    dev = []
    for i, c in enumerate(cases[:30]):
        clone = dict(c)
        clone["id"] = f"dev-{i + 1:02}"
        clone["objective"] = (
            c["objective"].replace("11月", "10月").replace("12月", "9月").replace("5月", "3月")
        )
        if clone.get("expected_filters", {}).get("month"):
            clone["expected_filters"] = {
                "month": [{"Nov": "Oct", "Dec": "Sep", "May": "Mar"}[clone["expected_filters"]["month"][0]]]
            }
        if not clone.get("expected_filters"):
            clone["objective"] = "仅看非周末会话。" + clone["objective"]
            clone["expected_filters"] = {"weekend": [False]}
        dev.append(clone)
    (directory / "development.json").write_text(
        json.dumps({"version": "1.0.0", "cases": dev}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Frozen: {len(cases)}; development: {len(dev)}")


if __name__ == "__main__":
    generate()
