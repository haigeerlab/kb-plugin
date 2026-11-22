# Capability Map: kb 插件（AI 知识复利系统 PCKS）

> 依据：[PRD](../docs/PRD.md)（2026-11-19 已批准）。**必须经人工审阅后才能往下走。**

## 目标

把干活时产生的经验和学到的东西，编译成持续生长、互相链接、带出处的个人知识库，让你和 AI 在任何项目里遇到新问题时都从已有积累起步；kb 以 Claude Code 插件加 Codex 可读的 Agent Skills 形态交付，对其他插件只做可选依赖。

<!-- 这一段是 Proposal 审查的目标指纹底本（`spec-digest.py` 计算）。
     改写目标会让已发布的 Proposal 被判为过期，所以改了先人工审阅；追加模块不需要改这里。
     标题必须是 `## 目标`（或 `## Goal`）—— 指纹脚本按标题定位这一节。 -->

## 模块

| Module id | Responsibility | Depends on |
|---|---|---|
| plugin-shell | 双宿主外壳：Claude Code 插件清单、Codex 可读的 skills 布局、知识库位置解析（固定配置，任何项目目录可用）、安装自检 | — |
| vault-contract | 知识库契约：SCHEMA.md、目录结构、5 种页面模板、frontmatter 与结论状态字段、`kb init`，以及确定性校验（出处逐字校验含状态块、index/log 一致性、断链、日期用本地时区） | plugin-shell |
| redaction | 写入前脱敏：密钥与凭证正则、本地黑名单（不进库）、项目代号替换；命中即拒绝写入并指出位置 | plugin-shell |
| save | `/kb save`：从当前会话提炼经验写入 inbox，当场编译成页（新建 / 合并 / 有冲突 / 无新内容），校验、预览、确认后写入并做一次本地 commit | vault-contract, redaction |
| ask | `/kb ask` 与 `--json` 契约、`interface.json`：index 加全文同义词检索，答案附出处，过时结论不当作现行答案 | vault-contract |
| lint | `/kb lint` 确定性体检：断链、孤儿页、index 不一致、出处不符、状态字段错误；安全修复；输出规模指标 | vault-contract |
| inbox-compile | `/kb compile`：批量处理 inbox 积压和候选会话（回读 transcript），逐条确认后入 wiki | save |
| session-capture | SessionEnd hook 静默记录候选会话指针（只记 transcript 路径和项目名，不复制内容） | vault-contract |
| delegate-lessons | 只读 delegate 的结果文件和答复，抽取 lessons 写入 inbox；不改 delegate | vault-contract, redaction |
| lint-semantic | 语义体检：疑似矛盾、疑似过期、缺页概念、建议升级为规则的条目 | lint |

Build order: plugin-shell → vault-contract → redaction → save → ask → lint → inbox-compile → session-capture → delegate-lessons → lint-semantic

<!-- Spec Guard 按严格串行推进。为兼容上游格式，逗号分组会按左到右顺序展开为单模块步骤，不代表并行授权。 -->

## 阶段对应

- **MVP（Phase 4）**：plugin-shell → vault-contract → redaction → save → ask → lint。做完后在真实项目上跑 PRD 第 9 节的验收。
- **集成（Phase 5）**：inbox-compile → session-capture → delegate-lessons → lint-semantic。
- **不在本图里**：
  - spec-guard 探测 kb 并提醒先 `/kb ask`：这是 spec-guard 仓库里的改动，按生态规则先登记 SEAMS、由总负责人出方案。kb 这边只负责在 ask 模块里发布 `interface.json`。
  - promote（Phase 6）、learn 和 hot cache（Phase 7）：等试用数据出来，再用 `add-module` 插入。
  - 发版命令（生态合并方案 S101 第三批 8.7，可调用的 check/prepare/publish 步骤，发布上限 auto-confirm）：用户 2026-11-22 决定延期。恢复条件：kb 实际开启自动接管（前提 spec-guard 接管配置与机器人身份已于 2026-11-22 就绪：本机两侧 spec-guard 0.92.0），或 kb 第一次需要从 GitHub 安装到另一台机器；届时用 `add-module` 插入并走 Spec。

---

## 审阅记录

- [x] 模块边界确认（砍掉或替换一个模块，不需要重写其他模块的需求）
- [x] 依赖方向单向无环（互相依赖 = 它们本来就是一个模块）
- [x] module id 已定稿（kebab-case，之后绝不改名 —— 同一个 id 同时是
      `spec/<id>.md`、`tasks/<id>/`、`.agent/state.json` 的 `activeModule` 和 Proposal 中的模块名，
      已发布的 Proposal 改不动）
- [x] 构建顺序符合依赖拓扑

审阅人：用户（对话中明确批准）
日期：2026-11-19

## 变更记录

- 2026-11-22：「不在本图里」新增发版命令一项（延期及恢复条件）；模块与构建顺序不变。
