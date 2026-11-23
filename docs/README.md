# 文档导航

[项目首页](../README.md) · [体验公开案例](https://ovo-daisy28.github.io/marketing-analysis-agent/)

面向营销运营的分析与报告 POC：通过报表 Skill 交付结果，通过研究 Loop 处理多轮分析。你可以按需要选择阅读深度。

| 阅读目的 | 推荐顺序 | 你会看到什么 |
|---|---|---|
| 快速了解项目 | [首页](../README.md) → 在线案例 | 用户问题、界面、当前架构与验证边界 |
| 评审解决方案 | [方案报告](solution-analysis.md) | 场景需求 → 官方产品对标 → 设计取舍 → 优化架构与验收要求 |
| 评审开发能力 | [当前架构](architecture.md) → [接口说明](api.md) | 工具调用、上下文、数据血缘、状态和恢复 |
| 复现与验证 | [运行指南](operations.md) → [评测协议](evaluation.md) → [验证记录](validation.md) | 启动方法、评测条件、历史结果和失败限制 |
| 评审企业接入 | [POC 验证](validation.md) → [交付与推广分析](delivery-analysis.md) | 接入条件、成本假设、风险、实施门槛及试点价值核算 |

## 当前实现与目标设计

| 状态 | 内容 | 权威入口 |
|---|---|---|
| 已实现 | 工具调用、受控报告、研究状态、数据库任务队列、版本发布 | 源码、[当前架构](architecture.md)、运行后的 `/openapi.json` |
| 历史验证 | 指定日期和版本的工程测试、模型对照、数值核对 | [验证记录](validation.md)与其中的原始结果链接 |
| 拟议增强 | TaskContract、澄清确认、范围校验、完整发布快照、受控远程试用 | [方案报告第三部分](solution-analysis.md#target-design) |

“实现了结构检查”不等于“结论准确”，“存在部署文件”不等于“企业生产上线”。优化设计不能当作当前运行能力。

## 图表索引

| 图表 | 回答的问题 | 位置 |
|---|---|---|
| 当前系统总览 | 系统由哪些可运行单元组成？ | [架构 SVG](diagrams/architecture-current.svg) |
| 当前数据血缘 | 数字和结论如何进入报告？ | [数据流 SVG](diagrams/data-flow-current.svg) |
| 接口时序 | 创建任务后谁调用谁，何时交付？ | [接口文档](api.md#sequence) |
| 当前任务状态 | 何时继续、等待、完成或停止？ | [状态图](architecture.md#reliability) |
| 当前部署 | 哪些服务在本机，哪些依赖外部？ | [部署 SVG](diagrams/deployment-current.svg) |
| 目标方案 | 下一阶段准备增加什么，为什么？ | [优化架构与流程](solution-analysis.md#target-design) |

图表可编辑源文件、样式和参考模板见[图表维护说明](diagrams/README.md)。

## 代码阅读顺序

1. [analytics.py](../marketing/analytics.py)、[schemas.py](../marketing/schemas.py)：数据合同和确定性计算。
2. [报表 Skill](../skills/report/SKILL.md)、[services.py](../marketing/services.py)：模板、报告状态和版本。
3. [tools.py](../marketing/tools.py)：function calling 定义、参数校验与执行。
4. [context.py](../marketing/context.py)、[worker.py](../marketing/worker.py)：研究上下文、主循环、租约和预算。
5. [api.py](../marketing/api.py)、[前端源码](../web/src)：会话、工作台、隔离预览和 SSE。

文档更新日期：2026-11-24。本轮复核 POC 口径并补充发布接口回归及交付分析，未重新运行真实模型评测。
