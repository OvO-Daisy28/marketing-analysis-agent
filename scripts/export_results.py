"""Publish compact, all-case results plus selected public-data traces; excludes DBs and credentials."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from marketing.config import ROOT


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="artifacts/eval-v1")
    args = p.parse_args()
    source = Path(args.source)
    target = ROOT / "docs/results"
    target.mkdir(parents=True, exist_ok=True)
    summary = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    (target / "evaluation-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    selected = {
        "report-02-full-1",
        "report-18-full-1",
        "research-01-full-1",
        "research-03-full-1",
        "research-10-full-1",
        "research-15-full-1",
        "boundary-1-full-1",
    }
    compact = []
    for file in sorted(source.glob("*.json")):
        result = json.loads(file.read_text(encoding="utf-8"))
        if "case_id" not in result:
            continue
        row = {k: v for k, v in result.items() if k not in {"evidence", "claims", "reports", "events"}}
        row["raw_sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
        compact.append(row)
        if file.stem in selected:
            shutil.copyfile(file, target / file.name)
    (target / "all-cases.json").write_text(
        json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    review = source / "semantic-review.json"
    if review.exists():
        shutil.copyfile(review, target / review.name)
    for folder, name in [
        ("eval-development", "development-summary.json"),
        ("eval-repeats", "repeat-summary.json"),
    ]:
        path = ROOT / "artifacts" / folder / "summary.json"
        if path.exists():
            shutil.copyfile(path, target / name)
    evidence_n = sum(len(x["numerical_checks"]) for x in compact)
    for variant in ["full", "baseline"]:
        normal = [x for x in compact if x["variant"] == variant and x["category"] in {"report", "research"}]
        print(
            variant,
            "normal_completed",
            sum(x["structural_success"] for x in normal),
            "/",
            len(normal),
            "intent",
            sum(x["intent_matched"] for x in normal),
        )
    print("published_cases", len(compact), "independent_numerical_checks", evidence_n)


if __name__ == "__main__":
    main()
