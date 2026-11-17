# GPT Researcher 复用说明

- 上游：https://github.com/assafelovic/gpt-researcher/blob/master/multi_agents/agents/reviewer.py
- 上游许可：Apache License 2.0，见本目录 LICENSE。`reviewer.upstream.py.txt` 为取得的原始参考文件，未作为运行代码。
- `safety_report/gptr_reviewer.py` 为基于上游审稿 Agent 改造的运行代码：对接本项目模型接口、结构化返回、章节证据和中文安全报告审查要求；取消上游的网络/模型依赖和不可靠的 None 字符串判断。
- 参考文件按 2026-11-17 获取，因网络环境无法确认上游 git commit，正式交付前须固定可核验版本并复核上游许可和 NOTICE。
- 审稿模型只能提示问题，不代表专业复核，不保证事实正确或法规现行有效。

## 完整 Python 软件包（0.17.0）

来源：PyPI 官方 `gpt-researcher==0.17.0` wheel，SHA-256 `01a230e487b24c36810fedf6f02555fb410cc6f46a1288c9940a42333ca2be7c`。`upstream-0.17.0` 原样展开其 Python 包和元数据；它不包含 GitHub 上的前端、完整仓库或所有上游可选功能。wheel 自带 Apache-2.0 LICENSE，但 METADATA 标示 MIT，许可标识不一致，商业交付前需要确认。

已接入并适配的能力：资料筛选（SourceCurator）、审稿流程和 BM25 本地证据排序。未自动运行上游的联网搜索、爬虫、MCP 或其他模型与数据服务；完整软件包也未安装到当前环境。`safety_report/gptr_bm25.py` 的 BM25 源自该 wheel 的 `gpt_researcher/context/lexical.py`，分词和传参针对中文及隔离规则修改。

## 固定提交完整 GitHub 源码

来源：https://github.com/assafelovic/gpt-researcher ，提交 `5cdad9cb434754188b78bd998df18dd8d502cf7e`。GitHub 源码压缩包 SHA-256 `193a3c169d6021712e95888b2efa30daad1e6181f55e25794284e1a1fdfa488b`。`gpt-researcher-source-5cdad9cb.tar.gz` 是该提交的完整归档，包括前后端、示例和测试资料，可按需解压查阅；此源码不表示已安装或启用所有组件。该源码与 PyPI wheel 是各自独立的固定版本，不能假定二者相同。
