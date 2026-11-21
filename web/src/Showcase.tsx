import React, { useEffect, useState } from "react";
import EvidencePanel, { percent, queryLabel } from "./EvidencePanel";
const ReportFrame = React.lazy(() => import("./ReportFrame"));
const repo = "https://github.com/OvO-Daisy28/marketing-analysis-agent";

export default function Showcase({
  onEnter,
  standalone = false,
}: {
  onEnter?: () => void;
  standalone?: boolean;
}) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState("");
  const [tab, setTab] = useState("report"),
    [evidence, setEvidence] = useState<any>(null);
  useEffect(() => {
    fetch(import.meta.env.BASE_URL + "showcase.json")
      .then((r) => {
        if (!r.ok) throw new Error("示例读取失败，请刷新重试");
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);
  return (
    <div className="showcase">
      <header className="showcase-nav">
        <a className="brand" href="#showcase">
          <span className="logo">S</span>SIGNAL
        </a>
        <div>
          <a href={repo} target="_blank" rel="noreferrer">
            GitHub ↗
          </a>
          {onEnter ? (
            <button onClick={onEnter}>创建自己的分析 →</button>
          ) : (
            <a className="button-link" href={repo + "#启动"}>
              启动真实分析 →
            </a>
          )}
        </div>
      </header>
      <main className="showcase-main">
        <div className="showcase-hero">
          <div>
            <p className="eyebrow">
              MARKETING ANALYSIS / INTERACTIVE CASE STUDY
            </p>
            <h1>
              从流量差异，
              <br />
              走到有依据的报告。
            </h1>
            <p>
              11 月哪些流量类型转化更好？新访客与回访者的差异，又能说明什么？
              <br />
              沿着目标、查询和证据，查看一份完整的营销分析交付。
            </p>
          </div>
          <div className="case-label">
            <span>公开案例 / 01</span>
            <b>12,330</b>
            <span>真实购物会话 · UCI 开放数据</span>
            <small>当前案例筛选 11 月，非全量统计</small>
          </div>
        </div>
        <div className="showcase-notice">
          <span className="outline-tag">固定示例</span>
          <p>
            数据由程序核算，分析步骤为预先编排的示例；此页面不调用模型。
            {standalone
              ? "真实 Agent、修改与发布功能请启动项目后体验。"
              : "创建工作区后，可让 Agent 针对你的问题重新分析。"}
          </p>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {!data ? (
          <p className="empty">正在读取公开案例…</p>
        ) : (
          <>
            <div className="case-kpis">
              <div>
                <span>11 月会话数</span>
                <strong>{data.data.totals.sessions.toLocaleString()}</strong>
              </div>
              <div>
                <span>购买会话数</span>
                <strong>{data.data.totals.purchases.toLocaleString()}</strong>
              </div>
              <div>
                <span>购买转化率</span>
                <strong>{percent(data.data.totals.conversion_rate)}</strong>
              </div>
              <div>
                <span>可核查查询</span>
                <strong>
                  {data.evidence.length}
                  <small> 组证据</small>
                </strong>
              </div>
            </div>
            <div className="case-layout">
              <section className="case-process">
                <p className="eyebrow">RESEARCH LOOP</p>
                <h2>一次分析，如何推进</h2>
                <p className="muted">
                  以下是可点击的示例步骤，真实任务由模型根据工具结果决定下一步。
                </p>
                {data.evidence.map((e: any, i: number) => (
                  <button
                    className="case-step"
                    key={e.id}
                    onClick={() => setEvidence(e)}
                  >
                    <span>0{i + 1}</span>
                    <div>
                      <strong>
                        {
                          [
                            "先比较流量表现",
                            "再检查访客结构",
                            "回到交叉分组验证",
                          ][i]
                        }
                      </strong>
                      <p>{queryLabel(e.query)}</p>
                      <small>查看查询结果 ↗</small>
                    </div>
                  </button>
                ))}
                <div className="case-boundary">
                  <b>结论边界</b>
                  <p>
                    差异可以帮助提出运营假设，但不能直接证明因果关系；没有成本与收入金额，因此不计算
                    ROI。
                  </p>
                </div>
                <a
                  href={repo + "/blob/main/docs/validation.md"}
                  target="_blank"
                  rel="noreferrer"
                >
                  查看真实模型评测与失败记录 ↗
                </a>
              </section>
              <section className="case-artifact">
                <div className="artifact-nav">
                  <div role="tablist" aria-label="案例视图">
                    <button
                      role="tab"
                      aria-selected={tab === "report"}
                      className={tab === "report" ? "chosen" : ""}
                      onClick={() => setTab("report")}
                    >
                      报告预览
                    </button>
                    <button
                      role="tab"
                      aria-selected={tab === "claims"}
                      className={tab === "claims" ? "chosen" : ""}
                      onClick={() => setTab("claims")}
                    >
                      结论与依据
                    </button>
                  </div>
                  <a
                    download
                    href={import.meta.env.BASE_URL + "sample-report.html"}
                  >
                    下载离线报告 ↓
                  </a>
                </div>
                {tab === "report" ? (
                  <React.Suspense
                    fallback={<p className="empty">正在加载图表…</p>}
                  >
                    <ReportFrame
                      version={data}
                      payload={data}
                      onError={setError}
                      onEvidence={(id) =>
                        setEvidence(data.evidence.find((e: any) => e.id === id))
                      }
                    />
                  </React.Suspense>
                ) : (
                  <div className="claim-list">
                    {data.claims.map((c: any, i: number) => (
                      <article key={c.id}>
                        <span className="eyebrow">FINDING 0{i + 1}</span>
                        <h3>{c.text}</h3>
                        <p>{c.limitation}</p>
                        {c.evidence_ids.map((id: string) => (
                          <button
                            className="secondary"
                            key={id}
                            onClick={() =>
                              setEvidence(
                                data.evidence.find((e: any) => e.id === id),
                              )
                            }
                          >
                            核对证据 ↗
                          </button>
                        ))}
                      </article>
                    ))}
                  </div>
                )}
              </section>
            </div>
            <div className="case-next">
              <div>
                <h2>换一个问题，观察 Agent 如何分析。</h2>
                <p>
                  报表 Skill 负责交付，研究 Loop
                  负责持续分析；你决定何时确认发布。
                </p>
              </div>
              {onEnter ? (
                <button onClick={onEnter}>进入自己的工作区 →</button>
              ) : (
                <a className="button-link" href={repo + "#启动"}>
                  按 README 启动项目 →
                </a>
              )}
            </div>
          </>
        )}
        <footer className="page-footer">
          SIGNAL / 开放数据 · 独立工程实现
          <span>UCI · CC BY 4.0 · 描述性分析</span>
        </footer>
      </main>
      {evidence && (
        <EvidencePanel
          key={evidence.id}
          evidence={evidence}
          onClose={() => setEvidence(null)}
        />
      )}
    </div>
  );
}
