import { useEffect, useRef, useState } from "react";
import frameScript from "./frame-bundle.js?raw";

export default function ReportFrame({
  version,
  onError,
}: {
  version: any;
  onError: (s: string) => void;
}) {
  const ref = useRef<HTMLIFrameElement>(null);
  const [documentHtml] = useState(() => {
    const nonce = crypto.randomUUID().replaceAll("-", "");
    return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"><style>body{font:14px system-ui;color:#263947;padding:26px;margin:0;background:white}h1{font-size:24px}#source,small{color:#7a8991;font-size:11px}#summary{padding:20px;background:#edf6f2;border-radius:10px;margin:20px 0;font-size:17px;font-weight:600}#chart{min-height:340px}td{padding:10px 18px;border-bottom:1px solid #ddd}#limitations{font-size:12px;line-height:1.8;color:#6c797f;margin-top:25px;border-top:1px solid #eee;padding-top:16px}small{overflow-wrap:anywhere}</style></head><body><p id="source"></p><h1 id="title">加载报告…</h1><div id="intro"></div><div id="summary"></div><div id="chart"></div><div id="claims"></div><div id="limitations"></div><script nonce="${nonce}">${frameScript.replaceAll("</script", "<\\/script")}</script></body></html>`;
  });
  useEffect(() => {
    const receive = async (e: MessageEvent) => {
      if (e.source !== ref.current?.contentWindow || e.origin !== "null")
        return;
      if (e.data?.type === "report-ready") {
        try {
          const response = await fetch("/api/report-versions/" + version.id, {
            credentials: "same-origin",
          });
          if (!response.ok) throw new Error("报告数据读取失败");
          const result = await response.json();
          ref.current?.contentWindow?.postMessage(
            { type: "report-data", payload: result },
            "*",
          );
        } catch (error) {
          onError(String(error));
          ref.current?.contentWindow?.postMessage(
            { type: "report-data", error: String(error) },
            "*",
          );
        }
      }
      if (e.data?.type === "report-error") onError(e.data.message);
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [version.id]);
  return (
    <iframe
      ref={ref}
      title="报表预览"
      sandbox="allow-scripts"
      srcDoc={documentHtml}
    />
  );
}
