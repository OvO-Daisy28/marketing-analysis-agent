"""Exercise the real PostgreSQL lease/CAS path; requires an initialized test database."""

import json
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from marketing import models as m
from marketing.config import settings
from marketing.db import Session, engine
from marketing.schemas import NewGoal
from marketing.services import create_goal
from marketing.worker import AgentLoop, claim_run


def main():
    if engine.dialect.name != "postgresql":
        raise SystemExit("This check requires PostgreSQL, not SQLite")
    settings.model_mode = "mock"
    workspace = m.uid()
    ids = []
    with Session.begin() as db:
        for i in range(6):
            g, r = create_goal(
                db,
                workspace,
                NewGoal(objective="Generate conversion report " + str(i), mode="report", request_key=m.uid()),
            )
            ids.append(r.id)
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda _: claim_run(), range(6)))
    assert len({c[0] for c in claims if c}) == 6
    with Session.begin() as db:
        first = db.get(m.Run, claims[0][0])
        first.lease_until = time.time() - 1
    recovered = claim_run()
    assert recovered[0] == claims[0][0] and recovered[1] != claims[0][1]
    AgentLoop().process(*claims[0])
    claims[0] = recovered
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda c: AgentLoop().process(*c), claims))
    with Session() as db:
        states = [db.get(m.Run, id).status for id in ids]
        assert states == ["completed"] * 6, states
        report_count = db.scalar(
            select(func.count()).select_from(m.Report).join(m.Goal).where(m.Goal.workspace_id == workspace)
        )
        assert report_count == 6
    print(
        json.dumps(
            {
                "backend": "PostgreSQL",
                "concurrent_claims": 6,
                "unique_runs": 6,
                "lease_recovery": True,
                "completed": 6,
                "reports": 6,
            }
        )
    )


if __name__ == "__main__":
    main()
