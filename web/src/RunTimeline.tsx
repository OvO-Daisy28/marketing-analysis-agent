import { queryLabel } from "./EvidencePanel";

const toolLabels: Record<string, string> = {
  data_contract: "确认数据范围与指标口径",
  query_metrics: "查询并计算营销指标",
  read_evidence: "核对已有证据",
  update_hypothesis: "更新分析假设",
  record_claim: "记录有依据的结论",
  draft_report: "生成报告草稿",
  finish: "检查交付条件",
  ask_user: "等待补充信息",
};
export const stopReasons: Record<string, string> = {
  TOKEN_BUDGET:
    "本次分析已达到 Token 预算，已有证据和草稿已保留。可以缩小问题范围后续接。",
  TIME_BUDGET: "本次分析达到时长限制，已保存进度。可以补充更具体的要求后续接。",
  STEP_BUDGET: "已达到单次分析轮次上限，建议缩小范围或明确下一步。",
  NO_PROGRESS: "连续分析未获得新进展，已主动停止。可以补充维度或重新限定问题。",
  WORKER_ERROR: "执行遇到内部错误，进度已保留。请检查服务日志后续接。",
  USER_CANCELLED: "已按你的要求停止，已获得的证据仍可查看。",
  MODEL_TIMEOUT: "模型服务响应超时，重试后仍未完成。请稍后续接。",
};
export default function RunTimeline({
  events,
  onEvidence,
}: {
  events: any[];
  onEvidence: (id: string) => void;
}) {
  return (
    <div className="timeline" aria-label="执行步骤">
      {events.map((e) => {
        const p = e.payload,
          result = p.result;
        let args: any = {};
        try {
          args =
            typeof p.arguments === "string"
              ? JSON.parse(p.arguments)
              : p.arguments || {};
        } catch {}
        const name =
          e.kind === "tool"
            ? toolLabels[p.name] || p.name
            : (
                {
                  model: "模型选择下一步",
                  model_error: "模型服务重试",
                  started: p.recovered ? "从检查点恢复" : "开始执行",
                  terminal: "本轮执行结束",
                  queued: "任务已进入队列",
                } as Record<string, string>
              )[e.kind] || e.kind;
        return (
          <details key={e.id}>
            <summary>
              <i
                className={
                  e.kind === "model_error" || result?.ok === false ? "warn" : ""
                }
              />
              <span>{name}</span>
              <small>
                {p.duration_ms !== undefined
                  ? (p.duration_ms / 1000).toFixed(1) + " 秒"
                  : new Date(e.created_at * 1000).toLocaleTimeString()}
              </small>
            </summary>
            {p.name === "query_metrics" && args.group_by && (
              <p>{queryLabel(args)}</p>
            )}
            {result?.ok === false && (
              <p className="warning">{result.error.message}</p>
            )}
            {result?.data?.evidence_id && (
              <button
                className="secondary"
                onClick={() => onEvidence(result.data.evidence_id)}
              >
                查看本次查询证据
              </button>
            )}
            <details className="raw-trace">
              <summary>技术详情</summary>
              <pre>{JSON.stringify(p, null, 2)}</pre>
            </details>
          </details>
        );
      })}
    </div>
  );
}
