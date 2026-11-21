"""Small real-provider probe. Reads credentials from .env; never prints them."""

import json
import time

from sqlalchemy import select

from marketing import models as m
from marketing.config import ROOT, settings
from marketing.db import Session
from marketing.schemas import NewGoal
from marketing.services import create_goal, serialize
from marketing.worker import AgentLoop, claim_run

assert settings.model_mode == "live", "Set MODEL_MODE=live in .env"
output = ROOT / "artifacts/live-smoke"
output.mkdir(parents=True, exist_ok=True)
for mode, objective in [
    ("report", "生成11月按流量类型分组的购买转化率报表，注明数据限制。"),
    (
        "research",
        "比较不同流量类型的购买转化表现，进一步检查新访客与回访者差异，检验一个假设并生成有证据的报告。",
    ),
]:
    with Session.begin() as db:
        goal, run = create_goal(
            db, "live-smoke", NewGoal(objective=objective, mode=mode, request_key=m.uid())
        )
        rid = run.id
    started = time.monotonic()
    claimed = claim_run()
    if not claimed or claimed[0] != rid:
        raise RuntimeError("Another queued task was found; run dedicated worker instead")
    AgentLoop().process(*claimed)
    with Session() as db:
        run = db.get(m.Run, rid)
        result = {
            "mode": mode,
            "status": run.status,
            "reason": run.stop_reason,
            "steps": run.steps,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "seconds": time.monotonic() - started,
            "model": settings.llm_model,
            "events": [
                serialize(e)
                for e in db.scalars(select(m.Event).where(m.Event.run_id == rid).order_by(m.Event.id))
            ],
        }
        (output / f"{mode}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps({k: v for k, v in result.items() if k != "events"}, ensure_ascii=False), flush=True)
        if run.status != "completed":
            break
