import { Chart } from "@antv/g2";

const root = document.getElementById("chart")!;
let chart: Chart | undefined;
window.addEventListener("message", async (e) => {
  if (e.source === parent && e.data?.type === "scroll-top") {
    window.scrollTo(0, 0);
    return;
  }
  if (e.source !== parent || e.data?.type !== "report-data") return;
  try {
    if (e.data.error) throw new Error(e.data.error);
    const { data, spec, claims, stale_claims } = e.data.payload;
    document.getElementById("title")!.textContent = spec.title;
    // intro_html has been validated by server; iframe still has an independent sandbox/CSP.
    document.getElementById("intro")!.innerHTML = spec.intro_html;
    document.getElementById("source")!.textContent =
      `UCI · 数据 ${data.dataset_id.slice(0, 12)} · 指标 ${data.metric_version}`;
    const scope = document.createElement("p");
    const names: Record<string, string> = {
      month: "月份",
      traffic_type: "流量类型",
      visitor_type: "访客类型",
      region: "地区编码",
      weekend: "周末",
    };
    scope.textContent =
      "实际数据范围：" +
      (Object.entries(data.query.filters)
        .filter(([, v]) => Array.isArray(v) && v.length)
        .map(([k, v]) => `${names[k]} ${String(v)}`)
        .join(" / ") || "全部会话") +
      " · 按" +
      (data.query.group_by.map((d: string) => names[d]).join(" × ") || "整体") +
      "汇总";
    scope.style.cssText =
      "font-size:12px;color:#567465;background:#f4f7f2;padding:10px;border-radius:6px";
    document.getElementById("intro")!.append(scope);
    const summary = document.getElementById("summary")!;
    summary.textContent = `会话 ${data.totals.sessions.toLocaleString()}   /   购买 ${data.totals.purchases.toLocaleString()}   /   转化率 ${data.totals.conversion_rate === null ? "无数据" : (data.totals.conversion_rate * 100).toFixed(2) + "%"}`;
    const claimBox = document.getElementById("claims")!;
    claimBox.replaceChildren();
    if (claims.length) {
      const label = document.createElement("h3");
      label.textContent = e.data.payload.delivery_label
        ? "示例分析 · 数据由程序核算"
        : "模型分析 · 发布前请结合证据核对";
      claimBox.append(label);
    }
    if (stale_claims)
      claimBox.textContent = "筛选条件已变化，旧结论已移除，请续接研究。";
    for (const c of claims) {
      const p = document.createElement("p");
      p.textContent = c.text;
      const small = document.createElement("small");
      small.textContent = c.limitation;
      const links = document.createElement("div");
      for (const id of c.evidence_ids) {
        const button = document.createElement("button");
        const index = (e.data.payload.evidence || []).findIndex((item:any) => item.id === id);
        button.textContent = `核对证据${index >= 0 ? " " + (index + 1) : ""} ↗`;
        button.style.cssText =
          "margin:10px 8px 18px 0;padding:8px 12px;border:1px solid #b6d5c8;border-radius:6px;background:#edf6f2;color:#176e62;cursor:pointer";
        button.addEventListener("click", () =>
          parent.postMessage({ type: "open-evidence", id }, "*"),
        );
        links.append(button);
      }
      claimBox.append(p, small, links);
    }
    document.getElementById("limitations")!.textContent =
      data.limitations.join(" ");
    chart?.destroy();
    root.replaceChildren();
    if (data.empty) {
      root.textContent = "当前筛选范围无数据";
      parent.postMessage({ type: "report-rendered", empty: true }, "*");
      return;
    }
    const months = [
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "June",
      "Jul",
      "Aug",
      "Sep",
      "Oct",
      "Nov",
      "Dec",
    ];
    const ordered = [...data.rows];
    if (data.query.group_by[0] === "month")
      ordered.sort(
        (a: any, b: any) => months.indexOf(a.month) - months.indexOf(b.month),
      );
    const rows = ordered.map((r: any) => ({
      ...r,
      label:
        data.query.group_by.map((k: string) => String(r[k])).join(" / ") ||
        "全部会话",
    }));
    const smallSamples = rows.filter((r: any) => r.small_sample).length;
    if (smallSamples) {
      const note = document.createElement("p");
      note.textContent = `${smallSamples} 个分组少于 30 条会话，转化率可能不稳定。请结合样本量阅读，不直接据此排序决策。`;
      note.style.cssText =
        "font-size:12px;color:#986d27;background:#fff7e5;padding:12px;border-radius:6px";
      root.append(note);
    }
    if (spec.chart === "table") {
      const table = document.createElement("table");
      const heading = document.createElement("tr");
      for (const label of ["分组", "会话数", "购买会话数", "购买转化率"]) {
        const th = document.createElement("th");
        th.textContent = label;
        heading.append(th);
      }
      table.append(heading);
      for (const r of rows) {
        const tr = document.createElement("tr");
        for (const v of [
          r.label,
          r.sessions,
          r.purchases,
          r.conversion_rate === null
            ? "—"
            : (r.conversion_rate * 100).toFixed(2) + "%",
        ]) {
          const td = document.createElement("td");
          td.textContent = String(v);
          tr.append(td);
        }
        table.append(tr);
      }
      root.append(table);
    } else {
      chart = new Chart({ container: root, autoFit: true, height: 340 });
      chart.options({
        type: spec.chart === "line" ? "line" : "interval",
        data: rows,
        encode: { x: "label", y: spec.metric },
        style: { fill: "#2a8f82" },
        axis: {
          x: { title: false, labelAutoRotate: true },
          y: {
            title:
              spec.metric === "conversion_rate"
                ? "购买转化率"
                : spec.metric === "sessions"
                  ? "会话数"
                  : "购买会话数",
            labelFormatter: (v: any) =>
              spec.metric === "conversion_rate"
                ? (Number(v) * 100).toFixed(0) + "%"
                : String(v),
          },
        },
        animate: false,
      });
      await chart.render();
    }
    parent.postMessage({ type: "report-rendered", empty: false }, "*");
  } catch (error) {
    root.textContent = "图表渲染失败：" + String(error);
    parent.postMessage({ type: "report-error", message: String(error) }, "*");
  }
});
parent.postMessage({ type: "report-ready" }, "*");
new ResizeObserver(() =>
  parent.postMessage(
    { type: "report-resize", height: document.body.scrollHeight },
    "*",
  ),
).observe(document.body);
