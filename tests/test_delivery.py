import csv
import io

from sqlalchemy import select

from marketing import models as m
from marketing.delivery import export_csv
from marketing.worker import work_once


def test_export_requires_publication_preserves_evidence_and_isolates_workspace(logged, factory):
    result = logged.post(
        "/api/goals",
        json={"objective": "研究流量和访客差异", "mode": "research", "request_key": "delivery-test"},
    ).json()
    assert work_once(factory)
    with factory.begin() as db:
        report = db.scalar(select(m.Report).where(m.Report.goal_id == result["goal"]["id"]))
        version = db.scalar(select(m.ReportVersion).where(m.ReportVersion.report_id == report.id))
        vid = version.id
        claim = db.get(m.Claim, version.spec["claim_ids"][0])
        claim.text = '<script>alert("bad")</script>'
    url = f"/api/report-versions/{vid}"
    payload = logged.get(url).json()
    evidence_ids = {e["id"] for e in payload["evidence"]}
    assert all(eid in evidence_ids for c in payload["claims"] for eid in c["evidence_ids"])
    assert logged.get(url + "/export").status_code == 409
    assert logged.post(url + "/publish", json={}).status_code == 200
    response = logged.get(url + "/export")
    assert response.status_code == 200
    assert "attachment;" in response.headers["content-disposition"]
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text
    assert "default-src" in response.text
    assert "fixture" in response.text
    for eid in evidence_ids:
        assert f'id="e-{eid}"' in response.text
    rows = list(csv.DictReader(io.StringIO(logged.get(url + "/export?format=csv").text.lstrip("\ufeff"))))
    assert sum(int(r["sessions"]) for r in rows) == payload["data"]["totals"]["sessions"]
    assert logged.get(url + "/export?format=pdf").status_code == 400
    logged.post("/api/auth/logout", json={})
    assert logged.get(url + "/export").status_code == 401
    logged.headers.pop("X-CSRF-Token", None)
    logged.post("/api/auth/register", json={"username": "another", "password": "test-password-123"})
    login = logged.post(
        "/api/auth/login", json={"username": "another", "password": "test-password-123"}
    ).json()
    logged.headers["X-CSRF-Token"] = login["csrf"]
    assert logged.get(url).status_code == 400
    assert logged.get(url + "/export").status_code == 400


def test_csv_escapes_spreadsheet_formula():
    payload = {
        "data": {
            "query": {"group_by": ["visitor_type"]},
            "rows": [
                {
                    "visitor_type": "=HYPERLINK(1)",
                    "sessions": 1,
                    "purchases": 0,
                    "conversion_rate": 0,
                    "small_sample": True,
                }
            ],
        }
    }
    assert "'=HYPERLINK(1)" in export_csv(payload)
