# 图表源文件与维护规范

[文档导航](../README.md) · [当前架构](../architecture.md) · [目标设计](../solution-analysis.md#target-design)

## 可编辑图表

| 视图 | GitHub 展示 | 可编辑源文件 | 范围 |
|---|---|---|---|
| 系统总览 | [SVG](architecture-current.svg) | [draw.io](architecture-current.drawio) | 当前实现，C4 容器层；非 Docker 容器清单 |
| 数据血缘 | [SVG](data-flow-current.svg) | [draw.io](data-flow-current.drawio) | 当前实现，数据与引用关系；不表示调用时序 |
| 部署 | [SVG](deployment-current.svg) | [draw.io](deployment-current.drawio) | 当前本机 Compose 与静态 Pages；非公网生产部署 |
| 研究循环 | [SVG](research-loop-current.svg) | [draw.io](research-loop-current.drawio) | 当前自建循环与上下文 |
| 任务状态 | [SVG](run-state-current.svg) | [draw.io](run-state-current.drawio) | 当前主要状态路径 |
| 业务流程 | [SVG](scenario-target.svg) | [draw.io](scenario-target.drawio) | 目标业务流程 |
| 目标架构 | [SVG](architecture-target.svg) | [draw.io](architecture-target.drawio) | 拟议增强，尚未实现 |
| 澄清续接 | [SVG](clarification-target.svg) | [draw.io](clarification-target.drawio) | 拟议确认事务与新旧 Run |
| 目标部署 | [SVG](deployment-target.svg) | [draw.io](deployment-target.drawio) | 拟议受控远程试用 |

接口时序图直接维护在 [api.md](../api.md#sequence) 与[方案报告](../solution-analysis.md#target-design)的 Mermaid 代码块中。消息箭头为直线；结构图和状态图使用固定布局 SVG，避免自动路由产生折线。

## 编辑与导出

1. 在 draw.io 桌面版或 [diagrams.net](https://app.diagrams.net/) 中打开 `.drawio` 文件。
2. 修改内容后保存源文件，再导出同名 SVG；选择白色背景，保持画布宽度 1120，避免裁掉图注。
3. SVG 使用普通文字和矢量图形，不依赖远程字体或图片；保留 `.drawio` 供继续编辑。
4. 检查 GitHub 默认宽度与深色页面下的可读性，确认模块名、图例和来源链接没有截断；同步更新相应说明。

初版 SVG 与 draw.io 从同一布局生成，二者表达相同内容。后续以 `.drawio` 为可编辑源，改图时必须同步导出，避免图源与展示图不一致。

## 图表表达规则

- **连接线必须是单段直线，不使用折线或曲线。**通过移动节点避免穿过其他模块；时序图允许虚线消息，但不能转折。
- 每张图只回答一个问题：组成、数据血缘、交互顺序、状态或部署位置。
- 节点采用“模块名＋职责”，连接标记数据或协议；系统边界与外部依赖显式标注。
- 深蓝 `#1E3A5F` 表示应用服务，青绿 `#0F766E` 表示数据与证据，灰色表示人员或外部依赖。
- 琥珀色 `#B45309` 可标识待确认或拟议内容，同时必须写明文字；颜色不能成为唯一状态编码。
- 白色不透明背景、中文系统字体、简短标签；首页只放总览，详细接口和异常放到正文。
- 当前图与目标图分开。标“拟议”的部署或模块，不能用作已上线证明。

## 参考模板与借鉴范围

这些链接用于文档组织与制图参考，本仓库没有复制厂商架构图或商业图标。

| 资料 | 采用什么 | 不照搬什么 |
|---|---|---|
| [GitHub README 指南](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes) | 用途、价值、上手入口、相对链接 | 不把全部开发文档堆在首页 |
| [Azure AI 参考架构](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/architecture/basic-microsoft-foundry-chat) | 图后解释流程、组件、取舍与 POC 边界 | 不将 Azure 托管服务画成本项目依赖 |
| [Azure RAG 示例仓库](https://github.com/Azure-Samples/azure-search-openai-demo) | 案例、运行、部署与详细资料互相连接 | 不复制其云部署与成本承诺 |
| [arc42 模板](https://arc42.org/overview/) | 问题、约束、策略、运行、部署、质量与风险 | 不要求填满全部十二章 |
| [C4 图表](https://c4model.com/diagrams) | 区分系统、容器、组件与部署层次 | 不把每个 Python 类画进首页 |
| [draw.io C4 图形库](https://www.drawio.com/docs/diagram-types/c4-modelling/) | 可编辑的节点、边界与关系 | 不依赖特定云平台图标 |
| [draw.io 数据流图](https://www.drawio.com/docs/diagram-types/data-flow-diagrams/) | 数据流与控制流区分 | 当前血缘图使用简化方框，不声称严格 DFD 标准符号 |
| [GitHub Mermaid](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams) / [时序图语法](https://mermaid.js.org/syntax/sequenceDiagram.html) | 随文档维护并原生渲染 | 不使用未检查兼容性的实验语法 |

整理日期：2026-11-24。图表记录该日期本地代码状态；业务变化后需重新核对。
