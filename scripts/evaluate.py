"""Bounded evaluation. Keeps model outcomes separate from deterministic engineering checks."""

import argparse
import csv
import hashlib
import json
import math
import platform
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from marketing import models as m
from marketing.analytics import latest_dataset
from marketing.config import ROOT, settings
from marketing.db import Base, Session, make_engine
from marketing.schemas import NewGoal
from marketing.services import create_goal, serialize
from marketing.worker import work_once


def oracle(raw_rows, query):
    """Independent CSV implementation: no business aggregate(), SQL or service metrics."""
    fields = {
        "month": "Month",
        "traffic_type": "TrafficType",
        "visitor_type": "VisitorType",
        "region": "Region",
        "weekend": "Weekend",
    }
    totals = defaultdict(lambda: [0, 0])
    for row in raw_rows:
        values = {
            k: (
                int(row[v])
                if k in {"traffic_type", "region"}
                else row[v].upper() == "TRUE"
                if k == "weekend"
                else row[v]
            )
            for k, v in fields.items()
        }
        if any(allowed and values[k] not in allowed for k, allowed in query["filters"].items()):
            continue
        group = tuple(values[k] for k in query["group_by"])
        totals[group][0] += 1
        totals[group][1] += int(row["Revenue"].upper() == "TRUE")
    if not query["group_by"] and not totals:
        totals[()] = [0, 0]
    return totals


def run_case(case, variant, dataset, raw_rows, output, repeat):
    label = f"{case['id']}-{variant}-{repeat}"
    database = output / (label + ".db")
    if database.exists():
        raise RuntimeError("Output already exists; use a new --output directory")
    engine = make_engine("sqlite:///" + str(database))
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with Session() as source, factory.begin() as db:
        db.add(m.Dataset(**dataset))
        db.flush()
        shopping = [
            {k: v for k, v in serialize(row).items() if k != "id"}
            for row in source.scalars(
                select(m.ShoppingSession).where(m.ShoppingSession.dataset_id == dataset["id"])
            )
        ]
        db.execute(m.ShoppingSession.__table__.insert(), shopping)
        g, r = create_goal(
            db, "evaluation", NewGoal(objective=case["objective"], mode=case["mode"], request_key=m.uid())
        )
        r.context_mode = "structured" if variant == "full" else "history"
        rid, gid = r.id, g.id
    started = time.monotonic()
    work_once(factory)
    elapsed = time.monotonic() - started
    with factory() as db:
        run = db.get(m.Run, rid)
        evidence = list(db.scalars(select(m.Evidence).where(m.Evidence.goal_id == gid)))
        claims = list(db.scalars(select(m.Claim).where(m.Claim.goal_id == gid)))
        report_ids = list(db.scalars(select(m.Report.id).where(m.Report.goal_id == gid)))
        versions = list(db.scalars(select(m.ReportVersion).where(m.ReportVersion.report_id.in_(report_ids))))
        numerical = []
        for e in evidence:
            gold = oracle(raw_rows, e.query)
            rows = e.result["rows"]
            correct = len(gold) == len(rows)
            for row in rows:
                pair = gold.get(tuple(row[k] for k in e.query["group_by"]))
                correct = correct and pair == [row["sessions"], row["purchases"]]
                if pair:
                    expected = pair[1] / pair[0] if pair[0] else None
                    correct = correct and (row["conversion_rate"] == expected)
            correct = correct and sum(v[0] for v in gold.values()) == e.result["totals"]["sessions"]
            numerical.append(bool(correct))
        intent = any(
            set(case.get("expected_dimensions", [])).issubset(e.query["group_by"])
            and all(e.query["filters"].get(k) == v for k, v in case.get("expected_filters", {}).items())
            for e in evidence
        )
        if case["expected_status"] == "waiting_input":
            intent = True
        ids = {e.id for e in evidence}
        references = all(c.evidence_ids and set(c.evidence_ids).issubset(ids) for c in claims)
        result = {
            "case_id": case["id"],
            "category": case["category"],
            "variant": variant,
            "repeat": repeat,
            "mode": settings.model_mode,
            "model": settings.llm_model if settings.model_mode == "live" else "deterministic-mock-v1",
            "status": run.status,
            "reason": run.stop_reason,
            "structural_success": run.status == case["expected_status"],
            "intent_matched": intent,
            "numerical_checks": numerical,
            "valid_references": references,
            "semantic_support": "pending_human_review",
            "seconds": elapsed,
            "steps": run.steps,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "evidence": [serialize(e) for e in evidence],
            "claims": [serialize(c) for c in claims],
            "reports": [serialize(v) for v in versions],
            "events": [
                serialize(e)
                for e in db.scalars(select(m.Event).where(m.Event.run_id == rid).order_by(m.Event.id))
            ],
        }
    (output / (label + ".json")).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    engine.dispose()
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--suite", default="eval/frozen.json")
    p.add_argument("--variant", choices=["full", "baseline", "both"], default="full")
    p.add_argument("--limit", type=int, default=3)
    p.add_argument("--category", default="")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--token-budget", type=int, default=240000)
    p.add_argument("--output", default="artifacts/eval-" + str(int(time.time())))
    args = p.parse_args()
    source = Path(args.suite).read_bytes()
    cases = json.loads(source)["cases"]
    selected = [
        c for c in cases if "objective" in c and (not args.category or c["category"] == args.category)
    ][: args.limit]
    variants = ["full", "baseline"] if args.variant == "both" else [args.variant]
    jobs = [(c, v, i) for c in selected for v in variants for i in range(1, args.repeats + 1)]
    if len(jobs) * settings.max_run_tokens > args.token_budget:
        raise SystemExit(
            f"Conservative reservation requires {len(jobs) * settings.max_run_tokens} tokens; increase --token-budget explicitly or reduce cases."
        )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    with Session() as db:
        dataset = serialize(latest_dataset(db))
    raw_rows = list(csv.DictReader((ROOT / "data" / f"{dataset['id']}.csv").open(encoding="utf-8-sig")))
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_case, c, v, dataset, raw_rows, output, i) for c, v, i in jobs]
        for future in as_completed(futures):
            r = future.result()
            results.append(r)
            print(
                json.dumps(
                    {
                        k: r[k]
                        for k in [
                            "case_id",
                            "variant",
                            "status",
                            "intent_matched",
                            "seconds",
                            "input_tokens",
                            "output_tokens",
                        ]
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    summary = {
        "suite_sha256": hashlib.sha256(source).hexdigest(),
        "dataset_sha256": dataset["id"],
        "platform": platform.platform(),
        "python": platform.python_version(),
        "settings": {"max_steps": settings.max_steps, "max_run_tokens": settings.max_run_tokens},
        "mode": settings.model_mode,
        "model": settings.llm_model,
        "runs": len(results),
        "total_tokens": sum(r["input_tokens"] + r["output_tokens"] for r in results),
        "groups": {},
        "semantic_review": "pending; reference presence is not proof of semantic correctness",
        "engineering_cases": "Run pytest separately; never counted as model quality samples",
    }
    for variant in variants:
        group = [r for r in results if r["variant"] == variant]
        latencies = sorted(r["seconds"] for r in group)
        summary["groups"][variant] = {
            "n": len(group),
            "structural_completion": sum(r["structural_success"] for r in group) / len(group),
            "intent_match": sum(r["intent_matched"] for r in group) / len(group),
            "all_numerical_checks_pass": all(all(r["numerical_checks"]) for r in group),
            "p50_seconds": latencies[math.ceil(len(group) * 0.5) - 1],
            "p95_seconds": latencies[math.ceil(len(group) * 0.95) - 1],
        }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
