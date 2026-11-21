import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

let csrf = "";
async function api(path: string, body?: unknown, method?: string) {
  const response = await fetch("/api" + path, {
    method: method || (body ? "POST" : "GET"),
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
const key = () => crypto.randomUUID();
const labels: Record<string, string> = {
  queued: "等待执行",
  running: "分析中",
  waiting_input: "需要补充",
  completed: "分析完成",
  stopped: "已停止",
  failed: "执行失败",
  cancelled: "已取消",
};

const ReportFrame = React.lazy(() => import("./ReportFrame"));

function App() {
  const [user, setUser] = useState<any>(null),
    [checking, setChecking] = useState(true);
  const [mode, setMode] = useState<any>({ mode: "mock" }),
    [page, setPage] = useState("workspace");
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [newAccount, setNewAccount] = useState(false);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [goals, setGoals] = useState<any[]>([]),
    [reports, setReports] = useState<any[]>([]),
    [detail, setDetail] = useState<any>(null);
  const [objective, setObjective] = useState(""),
    [taskMode, setTaskMode] = useState("research"),
    [events, setEvents] = useState<any[]>([]);
  const [followup, setFollowup] = useState(""),
    [selected, setSelected] = useState<any>(null),
    [editTitle, setEditTitle] = useState(""),
    [editChart, setEditChart] = useState("bar"),
    [month, setMonth] = useState("");
  const [contract, setContract] = useState<any>(null);
  const currentRun = detail?.runs?.at(-1);

  const refresh = async () => {
    const [g, r, c] = await Promise.all([
      api("/goals"),
      api("/reports"),
      api("/data/contract"),
    ]);
    setGoals(g);
    setReports(r);
    setContract(c);
  };
  const openGoal = async (id: string) => {
    const d = await api("/goals/" + id);
    setDetail(d);
    setPage("workspace");
    if (d.runs.length)
      setEvents(await api("/runs/" + d.runs.at(-1).id + "/events"));
  };
  const openVersion = async (id: string) => {
    const v = await api("/report-versions/" + id);
    setSelected(v);
    setEditTitle(v.spec.title);
    setEditChart(v.spec.chart);
    setMonth(v.query.filters.month?.[0] || "");
    setPage("reports");
  };
  const guarded = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    api("/health").then(setMode);
    api("/auth/me")
      .then((u) => {
        csrf = u.csrf;
        setUser(u);
      })
      .catch(() => {})
      .finally(() => setChecking(false));
  }, []);
  useEffect(() => {
    if (user) refresh().catch((e) => setError(String(e)));
  }, [user]);
  useEffect(() => {
    if (!currentRun || !["queued", "running"].includes(currentRun.status))
      return;
    const source = new EventSource("/api/runs/" + currentRun.id + "/stream");
    source.addEventListener("progress", (e) => {
      const item = JSON.parse((e as MessageEvent).data);
      setEvents((old) =>
        old.some((x) => x.id === item.id) ? old : [...old, item],
      );
    });
    source.addEventListener("done", () => {
      source.close();
      refresh()
        .then(() => openGoal(detail.goal.id))
        .catch((e) => setError(String(e)));
    });
    source.addEventListener("auth_expired", () => {
      source.close();
      setUser(null);
    });
    return () => source.close();
  }, [currentRun?.id]);

  async function authenticate(e: React.FormEvent) {
    e.preventDefault();
    await guarded(async () => {
      if (newAccount) await api("/auth/register", { username, password });
      const u = await api("/auth/login", { username, password });
      csrf = u.csrf;
      setUser(u);
      setPassword("");
    });
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await guarded(async () => {
      const result = await api("/goals", {
        objective,
        mode: taskMode,
        request_key: key(),
      });
      setEvents([]);
      await refresh();
      await openGoal(result.goal.id);
    });
  }
  async function revise() {
    await guarded(async () => {
      const changed = month !== (selected.query.filters.month?.[0] || "");
      const query = changed
        ? {
            ...selected.query,
            filters: { ...selected.query.filters, month: month ? [month] : [] },
          }
        : null;
      const v = await api("/reports/" + selected.report_id + "/revise", {
        base_version_id: selected.id,
        spec: { ...selected.spec, title: editTitle, chart: editChart },
        query,
        request_key: key(),
      });
      await refresh();
      await openVersion(v.id);
    });
  }

  if (checking) return <div className="loading">正在打开工作台…</div>;
  if (!user)
    return (
      <div className="auth-layout">
        <div className="auth-story">
          <div className="brand">
            <span className="logo">S</span> SIGNAL{" "}
            <small>MARKETING INTELLIGENCE</small>
          </div>
          <p className="eyebrow">从问题出发，以证据交付</p>
          <h1>
            让每一份报告，
            <br />
            都有迹可循。
          </h1>
          <p>
            把重复的报表流程交给 Skill。
            <br />
            把复杂的分析目标交给研究 Loop。
          </p>
          <div className="auth-grid">
            <div>
              01 <b>明确目标</b>
            </div>
            <div>
              02 <b>检验假设</b>
            </div>
            <div>
              03 <b>交付报告</b>
            </div>
          </div>
          <footer>公开电商数据 · 可追溯分析 · 人工确认发布</footer>
        </div>
        <form className="login" onSubmit={authenticate}>
          <p className="eyebrow">YOUR ANALYSIS SPACE</p>
          <h2>{newAccount ? "创建工作区" : "欢迎回到 Signal"}</h2>
          <p className="muted">
            {newAccount
              ? "每个账号拥有独立的分析与报告空间。"
              : "登录后继续你的分析与报告。"}
          </p>
          <label>
            用户名
            <input
              required
              minLength={3}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
          </label>
          <label>
            密码
            <input
              required
              minLength={10}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={newAccount ? "new-password" : "current-password"}
            />
          </label>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <button disabled={busy} type="submit">
            {busy
              ? "正在连接…"
              : newAccount
                ? "创建并进入工作台"
                : "进入工作台 →"}
          </button>
          <button
            type="button"
            className="text-button"
            onClick={() => {
              setNewAccount(!newAccount);
              setError("");
            }}
          >
            {newAccount ? "已有账号？登录" : "第一次使用？创建工作区"}
          </button>
          <small>
            密码至少 10 个字符 · 当前为
            {mode.mode === "live" ? "真实模型" : "确定性模拟"}模式
          </small>
        </form>
      </div>
    );

  return (
    <div className="app">
      <aside>
        <div className="brand">
          <span className="logo">S</span> SIGNAL
        </div>
        <p className="nav-label">MARKETING WORKSPACE</p>
        <nav>
          <button
            className={page === "workspace" ? "active" : ""}
            onClick={() => setPage("workspace")}
          >
            ◈ <span>分析工作台</span>
          </button>
          <button
            className={page === "reports" ? "active" : ""}
            onClick={() => setPage("reports")}
          >
            ▤ <span>报表中心</span>
            <small>{reports.length}</small>
          </button>
        </nav>
        <div className="sidebar-note">
          <span className="live-dot" />{" "}
          {mode.mode === "live" ? "真实模型已配置" : "确定性模拟模式"}
          <p>
            {mode.mode === "live"
              ? "每一步调用都有记录"
              : "模拟路径用于测试，不代表模型自主研究"}
          </p>
        </div>
        <div className="account">
          <span className="avatar">
            {user.username.slice(0, 1).toUpperCase()}
          </span>
          <div>
            {user.username}
            <small>个人工作区</small>
          </div>
          <button
            className="icon"
            title="退出登录"
            onClick={() =>
              guarded(async () => {
                await api("/auth/logout", {});
                setUser(null);
                setDetail(null);
                setSelected(null);
              })
            }
          >
            ↗
          </button>
        </div>
      </aside>
      <main>
        <header>
          <span>
            工作区 <span className="slash">/</span>{" "}
            {page === "workspace" ? "分析工作台" : "报表中心"}
          </span>
          <span className="dataset-badge">
            ● UCI OPEN DATA{" "}
            <b>{contract?.dataset.row_count?.toLocaleString() || "—"} 条会话</b>
          </span>
        </header>
        {error && (
          <div className="error global" role="alert">
            {error}
            <button className="icon" onClick={() => setError("")}>
              ×
            </button>
          </div>
        )}
        {page === "workspace" ? (
          <div className="page">
            <div className="page-heading">
              <div>
                <p className="eyebrow">RESEARCH & REPORT</p>
                <h1>从一个问题，开始分析。</h1>
                <p className="muted">
                  查数据、检验假设，把结果变成可以交付的报告。
                </p>
              </div>
              <span className="outline-tag">证据驱动 · 人工确认</span>
            </div>
            <section className="composer">
              <form onSubmit={submit}>
                <div className="segmented">
                  <button
                    type="button"
                    className={taskMode === "research" ? "chosen" : ""}
                    onClick={() => setTaskMode("research")}
                  >
                    多轮研究
                  </button>
                  <button
                    type="button"
                    className={taskMode === "report" ? "chosen" : ""}
                    onClick={() => setTaskMode("report")}
                  >
                    直接生成报表
                  </button>
                </div>
                <textarea
                  aria-label="分析需求"
                  placeholder={
                    taskMode === "research"
                      ? "例如：比较流量类型的购买转化，进一步检查访客结构是否影响差异…"
                      : "例如：生成 11 月按流量类型分组的购买转化率报表…"
                  }
                  value={objective}
                  onChange={(e) => setObjective(e.target.value)}
                  required
                  minLength={3}
                />
                <div className="composer-bottom">
                  <span>
                    支持流量、访客、月份等维度；不支持广告成本和 ROI。
                  </span>
                  <button type="submit" disabled={busy}>
                    {busy ? "正在创建…" : "开始分析 ↗"}
                  </button>
                </div>
              </form>
            </section>
            <div className="suggestions">
              <span>试试这些问题</span>
              {[
                "比较流量类型转化率，并检查新老访客差异",
                "生成11月按流量类型分组的转化率报表",
              ].map((t) => (
                <button
                  key={t}
                  onClick={() => {
                    setObjective(t);
                    setTaskMode(t.startsWith("生成") ? "report" : "research");
                  }}
                >
                  {t} ↗
                </button>
              ))}
            </div>
            <div className="workspace-grid">
              <section className="panel">
                <div className="section-head">
                  <h2>分析记录</h2>
                  <span>{goals.length} 个目标</span>
                </div>
                {!goals.length ? (
                  <div className="empty">
                    <b>你的第一条分析，从这里开始</b>
                    <p>目标、证据和报告会保存在工作区中。</p>
                  </div>
                ) : (
                  goals.map((g) => (
                    <button
                      className={
                        "goal-card " +
                        (detail?.goal.id === g.id ? "selected" : "")
                      }
                      key={g.id}
                      onClick={() => guarded(() => openGoal(g.id))}
                    >
                      <span className="task-type">
                        {g.mode === "research" ? "研究 LOOP" : "报表 SKILL"}
                      </span>
                      <strong>{g.objective}</strong>
                      <div>
                        <span className={"status " + g.runs.at(-1)?.status}>
                          {labels[g.runs.at(-1)?.status]}
                        </span>
                        <small>
                          {new Date(g.created_at * 1000).toLocaleDateString()}
                        </small>
                      </div>
                    </button>
                  ))
                )}
              </section>
              <section className="panel detail">
                <div className="section-head">
                  <h2>{detail ? "执行与证据" : "过程可见，结论可查"}</h2>
                  {currentRun && (
                    <span className={"status " + currentRun.status}>
                      {labels[currentRun.status]}
                    </span>
                  )}
                </div>
                {!detail ? (
                  <div className="empty diagram">
                    <span>目标 → 假设 → 证据 → 报告</span>
                    <p>
                      每一轮分析都围绕目标推进。
                      <br />
                      报告里的结论可以回到它的查询依据。
                    </p>
                  </div>
                ) : (
                  <>
                    <h3>{detail.goal.objective}</h3>
                    <div className="stats">
                      <div>
                        <b>{currentRun?.steps || 0}</b>
                        <span>模型轮次</span>
                      </div>
                      <div>
                        <b>{detail.evidence.length}</b>
                        <span>证据记录</span>
                      </div>
                      <div>
                        <b>
                          {(
                            (currentRun?.input_tokens || 0) +
                            (currentRun?.output_tokens || 0)
                          ).toLocaleString()}
                        </b>
                        <span>Token</span>
                      </div>
                    </div>
                    <div className="timeline">
                      {events.map((e) => (
                        <details key={e.id}>
                          <summary>
                            <i
                              className={e.kind === "model_error" ? "warn" : ""}
                            />
                            <span>
                              {e.kind === "tool"
                                ? e.payload.name
                                : e.kind === "model"
                                  ? "模型决策"
                                  : e.kind === "terminal"
                                    ? "执行结束"
                                    : e.kind === "model_error"
                                      ? "模型请求失败"
                                      : e.kind === "started"
                                        ? "开始执行"
                                        : "进入队列"}
                            </span>
                            <small>
                              {e.payload.duration_ms !== undefined
                                ? e.payload.duration_ms + " ms"
                                : new Date(
                                    e.created_at * 1000,
                                  ).toLocaleTimeString()}
                            </small>
                          </summary>
                          <pre>{JSON.stringify(e.payload, null, 2)}</pre>
                        </details>
                      ))}
                    </div>
                    {currentRun?.stop_reason && (
                      <p className="result-note">{currentRun.stop_reason}</p>
                    )}
                    {detail.hypotheses.map((h: any) => (
                      <details className="evidence" key={h.id}>
                        <summary>
                          假设 · {h.text} <small>{h.status}</small>
                        </summary>
                        <p>引用证据：{h.evidence_ids.join(", ") || "待查询"}</p>
                      </details>
                    ))}
                    {detail.evidence.map((e: any) => (
                      <details className="evidence" key={e.id}>
                        <summary>
                          证据 {e.id.slice(0, 8)} · {e.result.totals.sessions}{" "}
                          条会话
                        </summary>
                        <pre>{JSON.stringify(e, null, 2)}</pre>
                      </details>
                    ))}
                    {detail.reports.map((r: any) => (
                      <button
                        className="secondary"
                        key={r.id}
                        onClick={() =>
                          guarded(async () => {
                            await refresh();
                            const all = await api("/reports");
                            await openVersion(
                              all.find((x: any) => x.id === r.id).versions[0]
                                .id,
                            );
                          })
                        }
                      >
                        打开报告草稿 ↗
                      </button>
                    ))}
                    {["queued", "running"].includes(currentRun?.status) ? (
                      <button
                        className="text-button"
                        onClick={() =>
                          guarded(async () => {
                            await api("/runs/" + currentRun.id + "/cancel", {});
                            await openGoal(detail.goal.id);
                            await refresh();
                          })
                        }
                      >
                        停止当前执行
                      </button>
                    ) : (
                      <form
                        className="followup"
                        onSubmit={(e) => {
                          e.preventDefault();
                          guarded(async () => {
                            await api(
                              "/goals/" + detail.goal.id + "/continue",
                              { instruction: followup, request_key: key() },
                            );
                            setFollowup("");
                            await openGoal(detail.goal.id);
                          });
                        }}
                      >
                        <input
                          aria-label="补充分析要求"
                          value={followup}
                          onChange={(e) => setFollowup(e.target.value)}
                          placeholder="补充信息或提出新的分析要求…"
                          required
                        />
                        <button disabled={busy}>续接研究</button>
                      </form>
                    )}
                  </>
                )}
              </section>
            </div>
          </div>
        ) : (
          <div className="page">
            <div className="page-heading">
              <div>
                <p className="eyebrow">REPORT LIBRARY</p>
                <h1>把分析，变成可交付的报告。</h1>
                <p className="muted">
                  预览、调整、确认。每次修改都有独立版本。
                </p>
              </div>
            </div>
            <div className="report-grid">
              <section className="panel">
                <div className="section-head">
                  <h2>我的报告</h2>
                  <span>{reports.length} 份</span>
                </div>
                {!reports.length ? (
                  <div className="empty">
                    完成一次分析后，报告将出现在这里。
                  </div>
                ) : (
                  reports.map((r) => (
                    <div className="report-item" key={r.id}>
                      <strong>{r.versions[0].spec.title}</strong>
                      {r.versions.map((v: any) => (
                        <button
                          className={
                            "version " + (selected?.id === v.id ? "chosen" : "")
                          }
                          key={v.id}
                          onClick={() => guarded(() => openVersion(v.id))}
                        >
                          v{v.version}{" "}
                          <span>
                            {v.status === "published" ? "已发布" : "草稿"}
                          </span>
                        </button>
                      ))}
                    </div>
                  ))
                )}
              </section>
              <section className="panel preview">
                {selected ? (
                  <>
                    <div className="section-head">
                      <h2>
                        报告预览 <small>v{selected.version}</small>
                      </h2>
                      <span className="status">
                        {selected.status === "published"
                          ? "已发布 · 快照保留"
                          : "草稿 · 待确认"}
                      </span>
                    </div>
                    <div className="report-controls">
                      <label>
                        标题
                        <input
                          aria-label="报告标题"
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                        />
                      </label>
                      <label>
                        展示
                        <select
                          aria-label="展示形式"
                          value={editChart}
                          onChange={(e) => setEditChart(e.target.value)}
                        >
                          <option value="bar">柱状图</option>
                          <option value="line">折线图</option>
                          <option value="table">数据表</option>
                        </select>
                      </label>
                      <label>
                        月份
                        <select
                          aria-label="筛选月份"
                          value={month}
                          onChange={(e) => setMonth(e.target.value)}
                        >
                          <option value="">全部月份</option>
                          {[
                            "Feb",
                            "Mar",
                            "May",
                            "June",
                            "Jul",
                            "Aug",
                            "Sep",
                            "Oct",
                            "Nov",
                            "Dec",
                          ].map((m) => (
                            <option key={m}>{m}</option>
                          ))}
                        </select>
                      </label>
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={revise}
                      >
                        保存修改为新版本
                      </button>
                    </div>
                    {selected.stale_claims && (
                      <p className="warning">
                        筛选范围已改变，旧结论已移除。请续接分析以补充新结论。
                      </p>
                    )}
                    <React.Suspense
                      fallback={<div className="empty">正在加载图表组件…</div>}
                    >
                      <ReportFrame
                        key={selected.id}
                        version={selected}
                        onError={setError}
                      />
                    </React.Suspense>
                    <div className="publish-bar">
                      <small>数字来自固定数据版本 · 发布后保留快照</small>
                      <button
                        disabled={busy || selected.status === "published"}
                        onClick={() =>
                          guarded(async () => {
                            await api(
                              "/report-versions/" + selected.id + "/publish",
                              {},
                            );
                            await refresh();
                            await openVersion(selected.id);
                          })
                        }
                      >
                        {selected.status === "published"
                          ? "已确认发布"
                          : "确认发布此版本"}
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="empty diagram">
                    选择一份报告查看预览与版本。
                  </div>
                )}
              </section>
            </div>
          </div>
        )}
        <footer className="page-footer">
          SIGNAL / MARKETING ANALYSIS AGENT{" "}
          <span>公开复现项目 · 分析结果不代表因果效果</span>
        </footer>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
