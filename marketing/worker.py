import argparse
import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from pydantic import ValidationError
from sqlalchemy import and_, or_, select, update

from marketing import models as m
from marketing.config import settings
from marketing.context import ContextBuilder, tokens
from marketing.db import Session, engine
from marketing.provider import ProviderError, provider_for
from marketing.services import DomainError, event, state
from marketing.tools import ToolRegistry

log = logging.getLogger(__name__)
TERMINAL = {"waiting_input", "completed", "stopped", "failed", "cancelled"}


def claim_run(factory=Session):
    now, owner = time.time(), m.uid()
    with factory.begin() as db:
        condition = or_(m.Run.status == "queued", and_(m.Run.status == "running", m.Run.lease_until < now))
        candidate = db.scalar(
            select(m.Run)
            .where(condition)
            .order_by(m.Run.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not candidate:
            return None
        result = db.execute(
            update(m.Run)
            .where(m.Run.id == candidate.id, condition)
            .values(
                status="running",
                lease_owner=owner,
                lease_until=now + settings.lease_seconds,
                started_at=candidate.started_at or now,
            )
        )
        if result.rowcount != 1:
            return None
        event(db, candidate, "started", {"recovered": candidate.steps > 0})
        return candidate.id, owner


def locked(db, run_id, owner):
    run = db.scalar(select(m.Run).where(m.Run.id == run_id).with_for_update())
    if not run or run.status != "running" or run.lease_owner != owner or run.lease_until < time.time():
        return None
    return run


def heartbeat(stop, run_id, owner, factory):
    while not stop.wait(15):
        with factory.begin() as db:
            db.execute(
                update(m.Run)
                .where(
                    m.Run.id == run_id,
                    m.Run.lease_owner == owner,
                    m.Run.status == "running",
                    m.Run.lease_until >= time.time(),
                )
                .values(lease_until=time.time() + settings.lease_seconds)
            )


def progress_digest(db, goal):
    s = state(db, goal)
    del s["goal"]
    return hashlib.sha256(json.dumps(s, sort_keys=True, default=str).encode()).hexdigest()


def stop_run(db, run, status, reason):
    run.status, run.stop_reason, run.finished_at = status, reason, time.time()
    event(db, run, "terminal", {"status": status, "reason": reason})


class AgentLoop:
    def __init__(self, factory=Session, provider=None):
        self.factory, self.provider = factory, provider
        self.tools, self.context = ToolRegistry(), ContextBuilder()

    def process(self, run_id, owner):
        stop = threading.Event()
        thread = threading.Thread(target=heartbeat, args=(stop, run_id, owner, self.factory), daemon=True)
        thread.start()
        try:
            self._process(run_id, owner)
        except Exception:
            # Logs contain exception class/stack, never provider response bodies or credentials.
            log.exception("Worker failed for run %s", run_id)
            with self.factory.begin() as db:
                run = locked(db, run_id, owner)
                if run:
                    stop_run(db, run, "failed", "WORKER_ERROR")
        finally:
            stop.set()
            thread.join(timeout=2)

    def _process(self, run_id, owner):
        while True:
            with self.factory.begin() as db:
                run = locked(db, run_id, owner)
                if not run:
                    return
                goal = db.get(m.Goal, run.goal_id)
                if time.time() - run.started_at >= settings.max_run_seconds:
                    stop_run(db, run, "stopped", "TIME_BUDGET")
                    return
                if run.pending:
                    self._execute_pending(db, goal, run)
                    if run.status in TERMINAL:
                        run.finished_at = time.time()
                        event(db, run, "terminal", {"status": run.status, "reason": run.stop_reason})
                    continue
                if run.steps >= settings.max_steps or run.no_progress >= 3:
                    stop_run(db, run, "stopped", "NO_PROGRESS" if run.no_progress >= 3 else "STEP_BUDGET")
                    return
                try:
                    tool_schemas = self.tools.schemas_for(goal)
                    messages, context = self.context.build(db, goal, run, tool_schemas)
                except ValueError:
                    stop_run(db, run, "stopped", "CONTEXT_BUDGET")
                    return
                mode = run.provider_mode
                run.steps += 1
            # Each attempt reserves tokens before external I/O; uncertain calls remain charged on crash.
            for attempt in range(3):
                estimated = tokens(messages) + tokens(tool_schemas)
                with self.factory.begin() as db:
                    run = locked(db, run_id, owner)
                    if not run:
                        return
                    reserve = estimated + settings.max_output_tokens
                    if run.input_tokens + run.output_tokens + reserve > settings.max_run_tokens:
                        stop_run(db, run, "stopped", "TOKEN_BUDGET")
                        return
                    if time.time() - run.started_at >= settings.max_run_seconds:
                        stop_run(db, run, "stopped", "TIME_BUDGET")
                        return
                    run.input_tokens += estimated
                    run.output_tokens += settings.max_output_tokens
                started = time.monotonic()
                try:
                    answer = (self.provider or provider_for(mode)).chat(messages, tool_schemas, context)
                except ProviderError as exc:
                    with self.factory.begin() as db:
                        run = locked(db, run_id, owner)
                        if not run:
                            return
                        event(
                            db,
                            run,
                            "model_error",
                            {
                                "code": exc.code,
                                "attempt": attempt + 1,
                                "duration_ms": round((time.monotonic() - started) * 1000),
                            },
                        )
                        if not exc.retryable or attempt == 2:
                            stop_run(db, run, "failed", exc.code)
                            return
                    time.sleep(2**attempt)
                    continue
                with self.factory.begin() as db:
                    run = locked(db, run_id, owner)
                    if not run:
                        return
                    usage = answer.get("usage", {})
                    actual_in = max(0, int(usage.get("prompt_tokens", estimated)))
                    actual_out = max(0, int(usage.get("completion_tokens", tokens(answer["message"]))))
                    run.input_tokens += actual_in - estimated
                    run.output_tokens += actual_out - settings.max_output_tokens
                    event(
                        db,
                        run,
                        "model",
                        {
                            "model": answer.get("model"),
                            "mode": mode,
                            "duration_ms": round((time.monotonic() - started) * 1000),
                            "input_tokens": actual_in,
                            "output_tokens": actual_out,
                            "usage_estimated": "prompt_tokens" not in usage,
                            "protocol_adjustments": answer.get("protocol_adjustments", []),
                        },
                    )
                    if run.input_tokens + run.output_tokens > settings.max_run_tokens:
                        stop_run(db, run, "stopped", "TOKEN_BUDGET")
                        return
                    run.pending = {
                        "message": answer["message"],
                        "next": 0,
                        "before": progress_digest(db, db.get(m.Goal, run.goal_id)),
                    }
                break

    def _execute_pending(self, db, goal, run):
        pending = dict(run.pending)
        message = pending["message"]
        calls = message.get("tool_calls") or []
        index = pending["next"]
        if index == 0:
            run.messages = run.messages + [message]
        if not calls:
            run.messages = run.messages + [
                {"role": "user", "content": "请通过 finish 或 ask_user 结束；普通文本不会直接完成任务。"}
            ]
            run.no_progress += 1
            run.pending = None
            return
        call = calls[index]
        call_id = f"{run.steps}:{call['id']}"
        old = db.scalar(
            select(m.ToolExecution).where(
                m.ToolExecution.run_id == run.id, m.ToolExecution.call_id == call_id
            )
        )
        started = time.monotonic()
        if old:
            result = old.result
        else:
            name, args = call["function"]["name"], call["function"]["arguments"]
            try:
                parsed = json.loads(args) if isinstance(args, str) else args
                with db.begin_nested():
                    result = {"ok": True, "data": self.tools.execute(db, goal, run, name, parsed, call_id)}
            except (ValueError, ValidationError, DomainError) as exc:
                result = {
                    "ok": False,
                    "error": {"code": "INVALID_TOOL_REQUEST", "message": str(exc)[:1000], "retryable": False},
                }
            db.add(m.ToolExecution(run_id=run.id, call_id=call_id, name=name, result=result))
            event(
                db,
                run,
                "tool",
                {
                    "name": name,
                    "arguments": args,
                    "result": result,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                },
            )
        run.messages = run.messages + [
            {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)}
        ]
        pending["next"] = index + 1
        if run.status != "running":
            # Preserve protocol pairing for any unexecuted calls in a terminal batch.
            for rest in calls[index + 1 :]:
                run.messages = run.messages + [
                    {"role": "tool", "tool_call_id": rest["id"], "content": '{"skipped":"run terminated"}'}
                ]
            run.pending = None
        elif pending["next"] == len(calls):
            db.flush()
            changed = pending["before"] != progress_digest(db, goal)
            signature = hashlib.sha256(
                json.dumps([c["function"] for c in calls], sort_keys=True).encode()
            ).hexdigest()
            run.no_progress = (
                0 if changed else (run.no_progress + 1 if signature == run.last_action_signature else 1)
            )
            run.last_action_signature = signature
            run.pending = None
        else:
            run.pending = pending


def work_once(factory=Session, provider=None):
    claimed = claim_run(factory)
    if not claimed:
        return False
    AgentLoop(factory, provider).process(*claimed)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.once:
        work_once()
        return
    concurrency = 1 if engine.dialect.name == "sqlite" else settings.worker_concurrency
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        active = set()
        while True:
            active = {f for f in active if not f.done()}
            if len(active) < concurrency:
                item = claim_run()
                if item:
                    active.add(pool.submit(AgentLoop().process, *item))
                    continue
            time.sleep(0.5)


if __name__ == "__main__":
    main()
