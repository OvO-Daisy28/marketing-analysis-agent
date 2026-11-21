import { useEffect, useRef, useState } from "react";

export const dimensions: Record<string, string> = {
  month: "月份",
  traffic_type: "流量类型",
  visitor_type: "访客类型",
  region: "地区编码",
  weekend: "周末",
};
export const displayValue = (v: unknown) =>
  ({
    New_Visitor: "新访客",
    Returning_Visitor: "回访者",
    Other: "其他访客",
    Nov: "11 月",
    Dec: "12 月",
    true: "是",
    false: "否",
  })[String(v)] || String(v);
export const percent = (v: number | null) =>
  v == null ? "—" : (v * 100).toFixed(2) + "%";
export function queryLabel(query: any) {
  const filters = Object.entries(query.filters || {})
    .filter(([, v]) => Array.isArray(v) && v.length)
    .map(
      ([k, v]) =>
        `${dimensions[k]}：${(v as unknown[]).map(displayValue).join("、")}`,
    );
  return `${query.group_by.map((d: string) => dimensions[d]).join(" × ") || "整体汇总"} · ${filters.join(" / ") || "全部数据"}`;
}

export default function EvidencePanel({
  evidence,
  onClose,
}: {
  evidence: any;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("sessions");
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  const result = evidence.result;
  const rows = [...result.rows]
    .filter((r: any) =>
      result.query.group_by
        .map((d: string) => displayValue(r[d]))
        .join(" ")
        .toLowerCase()
        .includes(search.toLowerCase()),
    )
    .sort((a, b) => (b[sort] ?? -1) - (a[sort] ?? -1));
  return (
    <dialog
      ref={ref}
      className="evidence-dialog"
      aria-labelledby="evidence-title"
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="drawer-heading">
        <div>
          <p className="eyebrow">SOURCE OF TRUTH</p>
          <h2 id="evidence-title">查询证据</h2>
        </div>
        <button className="secondary" onClick={onClose}>
          关闭证据
        </button>
      </div>
      <p className="query-caption">{queryLabel(evidence.query)}</p>
      <div className="metric-strip">
        <div>
          <b>{result.totals.sessions.toLocaleString()}</b>
          <span>会话数</span>
        </div>
        <div>
          <b>{result.totals.purchases.toLocaleString()}</b>
          <span>购买会话数</span>
        </div>
        <div>
          <b>{percent(result.totals.conversion_rate)}</b>
          <span>购买转化率</span>
        </div>
      </div>
      <p className="formula-note">
        购买转化率 = 购买会话数 ÷ 会话数；总体比例按总分子与总分母计算。
      </p>
      <div className="evidence-filter">
        <input
          aria-label="搜索证据分组"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索分组…"
        />
        <label>
          排序
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="sessions">样本量从高到低</option>
            <option value="conversion_rate">转化率从高到低</option>
          </select>
        </label>
      </div>
      <div className="data-table">
        <table>
          <thead>
            <tr>
              {result.query.group_by.map((d: string) => (
                <th key={d}>{dimensions[d]}</th>
              ))}
              <th>会话数</th>
              <th>购买数</th>
              <th>转化率</th>
              <th>样本提示</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r: any, i: number) => (
              <tr key={i}>
                {result.query.group_by.map((d: string) => (
                  <td key={d}>{displayValue(r[d])}</td>
                ))}
                <td>{r.sessions.toLocaleString()}</td>
                <td>{r.purchases.toLocaleString()}</td>
                <td>{percent(r.conversion_rate)}</td>
                <td>
                  {r.small_sample ? (
                    <span className="sample-warning">小样本 &lt; 30</span>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <p className="empty">当前条件没有匹配的分组。</p>}
      </div>
      <details className="source-details">
        <summary>数据版本与查询参数</summary>
        <p>证据 ID：{evidence.id}</p>
        <p>数据 SHA-256：{result.dataset_id}</p>
        <p>指标版本：{result.metric_version}</p>
        <pre>{JSON.stringify(evidence.query, null, 2)}</pre>
      </details>
      <p className="muted">
        公开 UCI 购物会话数据 · 匿名流量编码 · 描述性差异不代表因果关系。
      </p>
    </dialog>
  );
}
