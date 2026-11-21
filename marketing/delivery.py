"""Read-only report delivery. No model calls, scripts, or unescaped model HTML."""

import csv
import html
import io
import json

from marketing import models as m
from marketing.analytics import aggregate
from marketing.schemas import Query
from marketing.services import owned_version, scoped_evidence, serialize

LABELS = {
    "month": "月份",
    "traffic_type": "流量类型",
    "visitor_type": "访客类型",
    "region": "地区编码",
    "weekend": "周末",
}


def report_payload(db, version_id, workspace):
    version, _, goal = owned_version(db, version_id, workspace)
    evidence = scoped_evidence(db, goal.id, version.evidence_id)
    claims = [serialize(db.get(m.Claim, cid)) for cid in version.spec["claim_ids"]]
    evidence_ids = list(dict.fromkeys([evidence.id] + [eid for c in claims for eid in c["evidence_ids"]]))
    return {
        **serialize(version),
        "query": evidence.query,
        "claims": claims,
        "goal_id": goal.id,
        "evidence": [serialize(scoped_evidence(db, goal.id, eid)) for eid in evidence_ids],
        "data": version.snapshot
        if version.status == "published"
        else aggregate(db, goal.dataset_id, Query.model_validate(evidence.query)),
    }


def table_html(result):
    dims = result["query"]["group_by"]
    headers = [LABELS[d] for d in dims] + ["会话数", "购买会话数", "购买转化率", "样本提示"]
    rows = []
    for r in result["rows"]:
        rate = "—" if r["conversion_rate"] is None else f"{r['conversion_rate']:.2%}"
        values = [r[d] for d in dims] + [
            r["sessions"],
            r["purchases"],
            rate,
            "少于 30 条" if r.get("small_sample") else "",
        ]
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in values) + "</tr>")
    return (
        '<div class="table"><table><thead><tr>'
        + "".join(f"<th>{x}</th>" for x in headers)
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def export_html(payload):
    def esc(v):
        return html.escape(str(v))

    data, spec = payload["data"], payload["spec"]
    total = data["totals"]
    rate = "—" if total["conversion_rate"] is None else f"{total['conversion_rate']:.2%}"
    numbers = {e["id"]: i + 1 for i, e in enumerate(payload["evidence"])}
    claims = "".join(
        f"<li><p>{esc(c['text'])}</p><small>{esc(c['limitation'])}</small><p>"
        + " ".join(f'<a href="#e-{esc(e)}">证据 {numbers[e]}</a>' for e in c["evidence_ids"])
        + "</p></li>"
        for c in payload["claims"]
    )
    evidence = "".join(
        f'<section id="e-{esc(e["id"])}"><h3>证据 {i + 1}</h3><p>{esc(json.dumps(e["query"], ensure_ascii=False))}</p>{table_html(e["result"])}</section>'
        for i, e in enumerate(payload["evidence"])
    )
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>{esc(spec["title"])}</title><style>
body{{font:15px/1.8 system-ui,sans-serif;color:#213b38;background:#f4f6f3;margin:0}}main{{max-width:1000px;margin:auto;padding:48px 24px}}h1{{font-size:32px;line-height:1.3}}section{{background:white;padding:24px;margin:24px 0;border:1px solid #dce5de;border-radius:12px}}.kpi{{font-size:20px;background:#e1f0e9;padding:24px;border-radius:12px}}small{{color:#60756d}}.table{{overflow:auto}}table{{width:100%;border-collapse:collapse;white-space:nowrap}}td,th{{text-align:left;padding:10px;border-bottom:1px solid #e1e8e3}}a{{color:#087361}}@media print{{body{{background:white}}main{{padding:0}}section{{break-inside:avoid}}}}</style><main>
<small>SIGNAL / {esc(payload.get("delivery_label", "已发布报告"))} · v{esc(payload["version"])}</small><h1>{esc(spec["title"])}</h1>
<div class="kpi">{total["sessions"]:,} 条会话 · {total["purchases"]:,} 次购买 · 转化率 {rate}</div>
<section><h2>分析结论</h2><ul>{claims or "<li>本报告仅交付描述性数据。</li>"}</ul></section>
<section><h2>报告数据</h2>{table_html(data)}</section><h2>证据与查询范围</h2>{evidence}
<section><h2>数据与限制</h2><p>购买转化率 = 购买会话数 / 会话数；各组使用相同筛选范围。</p><ul>{"".join("<li>" + esc(x) + "</li>" for x in data["limitations"])}</ul><small>数据版本：{esc(data["dataset_id"])}<br>指标版本：{esc(data["metric_version"])}</small><p>数据来源：UCI Online Shoppers Purchasing Intention · CC BY 4.0 · DOI 10.24432/C5F88Q</p></section>
<footer>此文件为固定快照，可离线阅读或使用浏览器打印为 PDF。不会连接模型或查询新数据。</footer></main></html>"""


def export_csv(payload):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    dims = payload["data"]["query"]["group_by"]
    columns = dims + ["sessions", "purchases", "conversion_rate", "small_sample"]
    writer.writerow(columns)
    for row in payload["data"]["rows"]:
        values = []
        for column in columns:
            value = row.get(column)
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return "\ufeff" + output.getvalue()
