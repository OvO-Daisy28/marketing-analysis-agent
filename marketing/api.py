import asyncio
import hashlib
import json
import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from marketing import auth
from marketing import models as m
from marketing import services as s
from marketing.analytics import aggregate, contract, latest_dataset
from marketing.config import ROOT, settings
from marketing.db import Session, get_db
from marketing.schemas import ContinueRun, Credentials, NewGoal, Query, Revision

app = FastAPI(title="Marketing Analysis Agent", version="0.1.0")
attempts = defaultdict(deque)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return response


@app.exception_handler(IntegrityError)
async def conflict_handler(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=409, content={"detail": "并发写入冲突，请使用原幂等键重试"})


@app.exception_handler(ValueError)
async def domain_handler(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=400, content={"detail": str(exc)})


def identity(request: Request, db=Depends(get_db)):
    auth.check_origin(request)
    return auth.authenticate(db, request)[0]


def login_guard(request):
    auth.check_origin(request)
    key = request.client.host if request.client else "local"
    queue = attempts[key]
    now = time.monotonic()
    while queue and queue[0] < now - 60:
        queue.popleft()
    if len(queue) >= 15:
        raise HTTPException(429, "请求过于频繁，请稍后再试")
    queue.append(now)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "mode": settings.model_mode,
        "model": settings.llm_model if settings.model_mode == "live" else "deterministic-mock-v1",
    }


@app.post("/api/auth/register", status_code=201)
def register(body: Credentials, request: Request, db=Depends(get_db)):
    login_guard(request)
    user = auth.register(db, body.username, body.password)
    db.commit()
    return {"username": user.username, "workspace_id": user.workspace_id}


@app.post("/api/auth/login")
def login(body: Credentials, request: Request, response: Response, db=Depends(get_db)):
    login_guard(request)
    user, token, csrf = auth.login(db, body.username, body.password)
    db.commit()
    response.set_cookie(
        "marketing_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=86400,
    )
    return {"username": user.username, "csrf": csrf, "workspace_id": user.workspace_id}


@app.get("/api/auth/me")
def me(request: Request, db=Depends(get_db)):
    user, session = auth.authenticate(db, request)
    return {"username": user.username, "workspace_id": user.workspace_id, "csrf": session.csrf}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, user=Depends(identity), db=Depends(get_db)):
    token = request.cookies.get("marketing_session", "")
    db.execute(
        delete(m.AuthSession).where(m.AuthSession.token_hash == hashlib.sha256(token.encode()).hexdigest())
    )
    db.commit()
    response.delete_cookie("marketing_session")
    return {"ok": True}


@app.get("/api/data/contract")
def data_contract(user=Depends(identity), db=Depends(get_db)):
    return {**contract(), "dataset": s.serialize(latest_dataset(db))}


@app.post("/api/data/query")
def query(body: Query, user=Depends(identity), db=Depends(get_db)):
    return aggregate(db, latest_dataset(db).id, body)


@app.post("/api/goals", status_code=201)
def create_goal(body: NewGoal, user=Depends(identity), db=Depends(get_db)):
    goal, run = s.create_goal(db, user.workspace_id, body)
    db.commit()
    return {"goal": s.serialize(goal), "run": public_run(run)}


def public_run(run):
    return {k: v for k, v in s.serialize(run).items() if k not in {"messages", "pending", "lease_owner"}}


@app.get("/api/goals")
def goals(user=Depends(identity), db=Depends(get_db)):
    return [
        {
            **s.serialize(g),
            "runs": [
                public_run(r)
                for r in db.scalars(select(m.Run).where(m.Run.goal_id == g.id).order_by(m.Run.created_at))
            ],
        }
        for g in db.scalars(
            select(m.Goal)
            .where(m.Goal.workspace_id == user.workspace_id)
            .order_by(m.Goal.created_at.desc())
            .limit(100)
        )
    ]


@app.get("/api/goals/{goal_id}")
def goal_detail(goal_id: str, user=Depends(identity), db=Depends(get_db)):
    goal = s.owned_goal(db, goal_id, user.workspace_id)
    return {
        **s.state(db, goal),
        "runs": [
            public_run(r)
            for r in db.scalars(select(m.Run).where(m.Run.goal_id == goal.id).order_by(m.Run.created_at))
        ],
    }


@app.post("/api/goals/{goal_id}/continue")
def continue_goal(goal_id: str, body: ContinueRun, user=Depends(identity), db=Depends(get_db)):
    run = s.continue_goal(
        db, s.owned_goal(db, goal_id, user.workspace_id), body.instruction, body.request_key
    )
    db.commit()
    return public_run(run)


@app.post("/api/runs/{run_id}/cancel")
def cancel(run_id: str, user=Depends(identity), db=Depends(get_db)):
    run = s.owned_run(db, run_id, user.workspace_id)
    db.refresh(run, with_for_update=True)
    if run.status in {"queued", "running", "waiting_input"}:
        run.status, run.stop_reason, run.finished_at = "cancelled", "USER_CANCELLED", time.time()
        s.event(db, run, "terminal", {"status": run.status, "reason": run.stop_reason})
    db.commit()
    return public_run(run)


@app.get("/api/runs/{run_id}/events")
def events(run_id: str, after: int = 0, user=Depends(identity), db=Depends(get_db)):
    s.owned_run(db, run_id, user.workspace_id)
    return [
        s.serialize(e)
        for e in db.scalars(
            select(m.Event)
            .where(m.Event.run_id == run_id, m.Event.id > after)
            .order_by(m.Event.id)
            .limit(500)
        )
    ]


@app.get("/api/runs/{run_id}/stream")
def stream(run_id: str, request: Request, after: int = 0, user=Depends(identity), db=Depends(get_db)):
    s.owned_run(db, run_id, user.workspace_id)
    try:
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        raise HTTPException(400, "Invalid event cursor") from None

    async def generate():
        nonlocal cursor
        while not await request.is_disconnected():
            with Session() as session:
                # Recheck session expiry/revocation during long-lived subscriptions.
                try:
                    auth.authenticate(session, request)
                except HTTPException:
                    yield "event: auth_expired\ndata: {}\n\n"
                    return
                run = s.owned_run(session, run_id, user.workspace_id)
                rows = list(
                    session.scalars(
                        select(m.Event)
                        .where(m.Event.run_id == run_id, m.Event.id > cursor)
                        .order_by(m.Event.id)
                        .limit(200)
                    )
                )
                for e in rows:
                    cursor = e.id
                    yield f"id: {e.id}\nevent: progress\ndata: {json.dumps(s.serialize(e), ensure_ascii=False)}\n\n"
                if run.status not in {"queued", "running"} and len(rows) < 200:
                    yield f"event: done\ndata: {json.dumps(public_run(run), ensure_ascii=False)}\n\n"
                    return
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


@app.get("/api/reports")
def reports(user=Depends(identity), db=Depends(get_db)):
    rows = db.scalars(
        select(m.Report)
        .join(m.Goal)
        .where(m.Goal.workspace_id == user.workspace_id)
        .order_by(m.Report.created_at.desc())
        .limit(100)
    )
    return [
        {
            **s.serialize(r),
            "versions": [
                s.serialize(v)
                for v in db.scalars(
                    select(m.ReportVersion)
                    .where(m.ReportVersion.report_id == r.id)
                    .order_by(m.ReportVersion.version.desc())
                )
            ],
        }
        for r in rows
    ]


@app.get("/api/report-versions/{version_id}")
def version_detail(version_id: str, user=Depends(identity), db=Depends(get_db)):
    version, report, goal = s.owned_version(db, version_id, user.workspace_id)
    evidence = s.scoped_evidence(db, goal.id, version.evidence_id)
    claims = [s.serialize(db.get(m.Claim, cid)) for cid in version.spec["claim_ids"]]
    return {
        **s.serialize(version),
        "query": evidence.query,
        "claims": claims,
        "goal_id": goal.id,
        "data": version.snapshot
        if version.status == "published"
        else aggregate(db, goal.dataset_id, Query.model_validate(evidence.query)),
    }


@app.post("/api/reports/{report_id}/revise")
def revise(report_id: str, body: Revision, user=Depends(identity), db=Depends(get_db)):
    report = db.get(m.Report, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    goal = s.owned_goal(db, report.goal_id, user.workspace_id)
    version = s.revise_report(db, report, goal, body)
    db.commit()
    return s.serialize(version)


@app.post("/api/report-versions/{version_id}/publish")
def publish(version_id: str, user=Depends(identity), db=Depends(get_db)):
    version, _, _ = s.owned_version(db, version_id, user.workspace_id)
    s.publish(db, version)
    db.commit()
    return s.serialize(version)


if (ROOT / "web/dist").exists():
    app.mount("/", StaticFiles(directory=ROOT / "web/dist", html=True), name="web")
