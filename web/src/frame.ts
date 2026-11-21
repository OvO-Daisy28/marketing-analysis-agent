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
    const summary = document.getElementById("summary")!;
    summary.textContent = `会话 ${data.totals.sessions.toLocaleString()}   /   购买 ${data.totals.purchases.toLocaleString()}   /   转化率 ${data.totals.conversion_rate === null ? "无数据" : (data.totals.conversion_rate * 100).toFixed(2) + "%"}`;
    const claimBox = document.getElementById("claims")!;
    claimBox.replaceChildren();
    if (claims.length) {
      const label = document.createElement("h3");
      label.textContent = "模型分析 · 发布前请结合证据核对";
      claimBox.append(label);
    }
    if (stale_claims)
      claimBox.textContent = "筛选条件已变化，旧结论已移除，请续接研究。";
    for (const c of claims) {
      const p = document.createElement("p");
      p.textContent = c.text;
      const small = document.createElement("small");
      small.textContent = `证据 ${c.evidence_ids.join(", ")} · ${c.limitation}`;
      claimBox.append(p, small);
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
