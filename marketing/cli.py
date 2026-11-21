import argparse
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from marketing import models as m
from marketing.analytics import contract
from marketing.config import ROOT
from marketing.db import Session

SOURCE = "https://archive.ics.uci.edu/static/public/468/online+shoppers+purchasing+intention+dataset.zip"


def import_data(db, path=None):
    if path:
        content = Path(path).read_bytes()
        source = "local_csv"
    else:
        response = httpx.get(SOURCE, follow_redirects=True, timeout=60)
        response.raise_for_status()
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        content = archive.read("online_shoppers_intention.csv")
        source = SOURCE
    digest = hashlib.sha256(content).hexdigest()
    existing = db.get(m.Dataset, digest)
    if existing:
        return existing
    records = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    if not path and len(records) != 12330:
        raise ValueError("Unexpected UCI row count")
    dataset = m.Dataset(id=digest, source=source, row_count=len(records))
    db.add(dataset)
    db.flush()
    rows = []
    for r in records:
        if r["Revenue"].upper() not in {"TRUE", "FALSE"} or r["Weekend"].upper() not in {"TRUE", "FALSE"}:
            raise ValueError("Invalid boolean in dataset")
        rows.append(
            {
                "dataset_id": digest,
                "month": r["Month"],
                "traffic_type": int(r["TrafficType"]),
                "visitor_type": r["VisitorType"],
                "region": int(r["Region"]),
                "weekend": r["Weekend"].upper() == "TRUE",
                "purchased": r["Revenue"].upper() == "TRUE",
            }
        )
    db.execute(m.ShoppingSession.__table__.insert(), rows)
    directory = ROOT / "data"
    directory.mkdir(exist_ok=True)
    (directory / f"{digest}.csv").write_bytes(content)
    return dataset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init-db", "import-data", "contract", "references"])
    parser.add_argument("--csv")
    args = parser.parse_args()
    if args.action == "init-db":
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    elif args.action == "import-data":
        with Session.begin() as db:
            dataset = import_data(db, args.csv)
            print(json.dumps({"dataset_id": dataset.id, "rows": dataset.row_count, "source": dataset.source}))
    elif args.action == "contract":
        print(json.dumps(contract(), ensure_ascii=False, indent=2))
    else:
        refs = []
        for repo in ["bytedance/deer-flow", "aliyun/data-agent-skill", "eosphoros-ai/DB-GPT"]:
            response = httpx.get(f"https://api.github.com/repos/{repo}/commits/HEAD", timeout=30)
            response.raise_for_status()
            body = response.json()
            refs.append(
                {
                    "repository": "https://github.com/" + repo,
                    "commit": body["sha"],
                    "date": body["commit"]["committer"]["date"],
                    "reuse": "design reference only; no source copied",
                }
            )
        (ROOT / "docs/references.json").write_text(json.dumps(refs, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
