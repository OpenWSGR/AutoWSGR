# AI Issue Analysis Bot

该仓库已接入基于 `MistEO/ai-issue-analysis` 的 Issue 自动分析机器人。

## 已部署内容

- Workflow: `.github/workflows/ai-issue-analysis.yml`
- Skill: `.claude/skills/generic-issue-log-analysis/SKILL.md`

## 触发条件

- 新建 Issue (`opened`)
- 重新打开 Issue (`reopened`)
- 在 Issue 评论中提及 `@github-actions`
- 手动触发 `workflow_dispatch` 并传 `issue_number`

说明：PR 评论不会触发该分析流程。

## 必需 Secret

在仓库 `Settings -> Secrets and variables -> Actions` 中新增：

- `COPILOT_GITHUB_TOKEN`

该 token 需为 Fine-grained PAT，并具备 Copilot 相关权限（按 `MistEO/ai-issue-analysis` README 指引配置）。

## 运行与输出

每次运行会：

1. 在对应 Issue 创建/更新一条分析评论
2. 输出分析 prompt、Copilot 原始输出、最终结论
3. 上传运行产物（artifacts）用于排障

## 模型配置

- 工作流默认使用 `gpt-5.3-codex`。
- 可在仓库 `Settings -> Secrets and variables -> Actions -> Variables` 配置：
  - `COPILOT_MODEL`（例如 `gpt-5.3-codex`）
  - `COPILOT_REASONING_EFFORT`（例如 `high` / `xhigh`）
- 如果出现 `Model "..." from --model flag is not available.`，请改为账号可用模型或删除变量回落默认值。

## 使用建议

- 若要手动重跑某个 Issue：在 Actions 页面手动运行该 workflow，并填写 `issue_number`。
- 若要补充上下文让机器人重新分析：在该 Issue 下评论并 `@github-actions`。
- 若分析结果偏泛化，可继续在 `.claude/skills/generic-issue-log-analysis/SKILL.md` 中增加仓库专用规则。
