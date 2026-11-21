import time
import uuid

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from marketing.db import Base


def uid():
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    role: Mapped[str] = mapped_column(String(16), default="owner")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[float] = mapped_column(Float)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(Text)
    row_count: Mapped[int] = mapped_column(Integer)
    imported_at: Mapped[float] = mapped_column(Float, default=time.time)


class ShoppingSession(Base):
    __tablename__ = "shopping_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    month: Mapped[str] = mapped_column(String(12), index=True)
    traffic_type: Mapped[int] = mapped_column(Integer, index=True)
    visitor_type: Mapped[str] = mapped_column(String(40), index=True)
    region: Mapped[int] = mapped_column(Integer)
    weekend: Mapped[bool] = mapped_column(Boolean)
    purchased: Mapped[bool] = mapped_column(Boolean)


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (UniqueConstraint("workspace_id", "request_key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    objective: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(16))
    request_key: Mapped[str] = mapped_column(String(100))
    criteria: Mapped[list] = mapped_column(JSON, default=list)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("goal_id", "request_key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id"), index=True)
    request_key: Mapped[str] = mapped_column(String(100))
    instruction: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    stop_reason: Mapped[str] = mapped_column(Text, default="")
    provider_mode: Mapped[str] = mapped_column(String(16), default="mock")
    context_mode: Mapped[str] = mapped_column(String(24), default="structured")
    steps: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    no_progress: Mapped[int] = mapped_column(Integer, default=0)
    last_action_signature: Mapped[str] = mapped_column(String(64), default="")
    messages: Mapped[list] = mapped_column(JSON, default=list)
    pending: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class Hypothesis(Base):
    __tablename__ = "hypotheses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="open")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (UniqueConstraint("goal_id", "query_hash"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id"), index=True)
    query_hash: Mapped[str] = mapped_column(String(64))
    query: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list] = mapped_column(JSON)
    limitation: Mapped[str] = mapped_column(Text)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id"), index=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class ReportVersion(Base):
    __tablename__ = "report_versions"
    __table_args__ = (UniqueConstraint("report_id", "version"), UniqueConstraint("report_id", "request_key"))
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    request_key: Mapped[str] = mapped_column(String(100))
    request_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    spec: Mapped[dict] = mapped_column(JSON)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    stale_claims: Mapped[bool] = mapped_column(Boolean, default=False)
    snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    published_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (UniqueConstraint("run_id", "call_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    call_id: Mapped[str] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(String(80))
    result: Mapped[dict] = mapped_column(JSON)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
