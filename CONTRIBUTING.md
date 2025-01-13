# 贡献到 AutoWSGR

我们欢迎对 [AutoWSGR](https://github.com/OpenWSGR/AutoWSGR) 的贡献！在贡献之前，请阅读以下指南。

------

## 开发设置 Development Setup

1. 克隆仓库。

    ```bash
    git clone git@github.com:OpenWSGR/AutoWSGR.git
    cd AutoWSGR
    ```
2. 设置开发环境。

    ```bash
    conda create -n autowsgr python=3.12
    conda activate autowsgr
    pip install -e .

    pre-commit install
    ```

------

## 合并请求指导 Pull Request Guidelines

### 原则 Principles

1. **小的变更 Small Changes**: 做出小的、增量的变更，这些变更易于审查。
2. **清晰的提交信息 Clear Commit Messages**: 编写清晰、简洁的提交信息来解释变更。我们推荐使用 [Semantic Commit Messages](https://www.conventionalcommits.org/zh-hans/v1.0.0/) 格式。
3. **PR 描述 PR Description**: 在合并请求中提供变更的清晰描述。
4. **代码审查 Code Review**: 在创建合并请求之前审查自己的代码。在合并之前，获得至少一个其他团队成员的批准（不包括你自己）。
5. **测试 Testing**: 确保在创建合并请求之前本地测试代码，并确保在合并之前 CI/CD 流水线中的测试通过。

### 如何贡献 How to Contribute

1. 为你的特性或错误修复创建一个新的分支。
   1. 如果你不是项目管理者：从 GitHub 仓库 (<https://github.com/OpenWSGR/AutoWSGR>) 创建一个 Fork 仓库，随后克隆并创建自己的功能分支。

        ```bash
        git clone https://github.com/<yourname>/AutoWSGR
        cd AutoWSGR
        git checkout -b <my-feature-branch>
        ```

    2. 如果你是项目管理员：可以不用Fork，转为在主仓库创建一个分支。

        ```bash
        git fetch --all
        git checkout main
        git checkout -b <my-feature-branch>
        ```

2. 做出你的变更并将它们提交到分支。提交前不要忘记运行 `pre-commit` 检查。

3. 将你的变更推送到远程仓库并创建一个合并请求。

    ```bash
    git push -u origin <my-feature-branch>
    ```

4. 转到 GitHub 仓库 (<https://github.com/OpenWSGR/AutoWSGR>) 并创建一个新的合并请求。

5. 将合并请求分配给至少一个团队成员进行审查。在获得至少一个批准之前，**不要合并** 请求！

   在审查过程中，你可能需要根据反馈对代码进行更改。保持分支与 `main` 分支保持最新。

    ```bash
    git fetch --all
    git rebase -i origin/main
    ```

6. 合并请求获得批准后，压缩并将其合并到 `main` 分支中。

------

## 测试 Testing

在创建合并请求之前，请确保在本地测试你的变更。可以运行 [`examples`](./examples) 目录中的各种脚本进行测试。

------

## 文档 Documentation

如果你对代码库进行了更改，请更新 [用户文档](https://docs-autowsgr.notion.site/)。同样鼓励在代码中编写注释和文档字符串。

------

## 代码风格 Code Style

我们使用几种工具来确保代码质量，包括：

- Python 代码风格：`ruff`, `isort`, `black`
- 英语拼写检查：`codespell`

我们建议使用 `pre-commit` 工具在提交之前自动检查和格式化你的代码。

我们将逐步在 CI/CD 流水线中强制执行这些工具，以确保代码质量。

------

如果你有任何问题或需要帮助，请通过qq群568500514联系团队。
