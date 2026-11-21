import json

import httpx

from marketing.config import settings


class ProviderError(Exception):
    def __init__(self, code, retryable=False):
        self.code, self.retryable = code, retryable
        super().__init__(code)


class LiveProvider:
    def chat(self, messages, tools, context):
        if not settings.llm_api_key or not settings.llm_model:
            raise ProviderError("MODEL_NOT_CONFIGURED")
        try:
            response = httpx.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + settings.llm_api_key},
                json={
                    "model": settings.llm_model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": 0,
                    "max_tokens": settings.max_output_tokens,
                },
                timeout=settings.llm_timeout,
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            raise ProviderError("MODEL_NETWORK_TIMEOUT", True) from None
        if response.status_code >= 400:
            raise ProviderError(
                f"MODEL_HTTP_{response.status_code}", response.status_code in {408, 429, 500, 502, 503, 504}
            )
        try:
            body = response.json()
            raw = body["choices"][0]["message"]
            msg = {"role": "assistant", "content": raw.get("content") or ""}
            calls = raw.get("tool_calls") or []
            if len(calls) > 8:
                raise ValueError("too many tool calls")
            if calls:
                msg["tool_calls"] = [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["function"]["name"], "arguments": c["function"]["arguments"]},
                    }
                    for c in calls
                ]
                if len({c["id"] for c in calls}) != len(calls):
                    raise ValueError("duplicate call IDs")
            adjustments = []
            if settings.tool_arguments_empty_prefix_fix:
                for call in msg.get("tool_calls", []):
                    raw_args = call["function"]["arguments"]
                    if isinstance(raw_args, str) and raw_args.startswith("{}") and len(raw_args) > 2:
                        try:
                            decoded = json.loads(raw_args[2:])
                            if isinstance(decoded, dict):
                                call["function"]["arguments"] = raw_args[2:]
                                adjustments.append(
                                    {
                                        "call_id": call["id"],
                                        "fix": "empty_object_prefix",
                                        "original_arguments": raw_args,
                                    }
                                )
                        except ValueError:
                            pass
            usage = body.get("usage", {})
            return {
                "message": msg,
                "usage": usage,
                "model": body.get("model", settings.llm_model),
                "protocol_adjustments": adjustments,
            }
        except (ValueError, TypeError, KeyError, IndexError):
            raise ProviderError("MODEL_PROTOCOL_ERROR") from None


class MockProvider:
    """Deterministic fixture only. Never presented as autonomous model evaluation."""

    def chat(self, messages, tools, context):
        goal, run = context["goal"], context["run"]
        evidence, hypotheses, claims, reports = [
            context[k] for k in ("evidence", "hypotheses", "claims", "reports")
        ]
        # A continuation must deliver a new draft, even in the deterministic fixture.
        reports = [r for r in reports if r["created_at"] >= run["created_at"]]
        objective = run["instruction"]
        if any(x in objective.lower() for x in ["roi", "本周", "广告成本", "收入金额"]):
            name, args = (
                "ask_user",
                {"question": "公开数据没有日期、成本或收入金额，请改为月份/流量类型的购买转化分析。"},
            )
        elif run["steps"] == 0:
            name, args = "data_contract", {}
        elif goal["mode"] == "research" and not hypotheses:
            name, args = "update_hypothesis", {"text": "不同访客类型的观察转化率存在差异"}
        elif not evidence:
            dimensions = (
                ["visitor_type"] if "访客" in objective and goal["mode"] == "report" else ["traffic_type"]
            )
            if "月份" in objective:
                dimensions = ["month"]
            filters = {"month": ["Nov"]} if "11月" in objective else {}
            name, args = "query_metrics", {"group_by": dimensions, "filters": filters}
        elif goal["mode"] == "research" and len(evidence) < 2:
            name, args = "query_metrics", {"group_by": ["traffic_type", "visitor_type"]}
        elif hypotheses and hypotheses[0]["status"] == "open":
            h = hypotheses[0]
            name, args = (
                "update_hypothesis",
                {
                    "hypothesis_id": h["id"],
                    "text": h["text"],
                    "status": "inconclusive",
                    "evidence_ids": [e["id"] for e in evidence],
                },
            )
        elif not claims:
            e = evidence[0]
            totals = e["result"]["totals"]
            name, args = (
                "record_claim",
                {
                    "text": f"当前筛选范围含 {totals['sessions']} 条会话，其中 {totals['purchases']} 条发生购买。分组结果见图表。",
                    "evidence_ids": [e["id"]],
                    "limitation": "这是样本描述，不证明流量或访客类型导致购买。",
                },
            )
        elif not reports:
            name, args = (
                "draft_report",
                {
                    "evidence_id": evidence[0]["id"],
                    "spec": {
                        "title": "流量与购买转化分析",
                        "intro_html": "<p>基于公开购物会话数据，检查流量表现及样本限制。</p>",
                        "chart": "bar",
                        "metric": "conversion_rate",
                        "claim_ids": [c["id"] for c in claims],
                    },
                },
            )
        else:
            name, args = (
                "finish",
                {
                    "summary": "模拟流程完成，报告草稿可预览；该模式不代表真实模型自主研究。",
                    "criteria_coverage": goal["criteria"],
                },
            )
        return {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": f"mock-{run['id']}-{run['steps']}",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                    }
                ],
            },
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            "model": "deterministic-mock-v1",
        }


def provider_for(mode):
    if mode == "live":
        return LiveProvider()
    if mode == "mock":
        return MockProvider()
    raise ProviderError("UNKNOWN_MODEL_MODE")
