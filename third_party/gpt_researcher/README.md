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

## 2026-11-18 已写小节检索适配

`safety_report/gptr_bm25.py::rank_written_sections` 根据 wheel 中 `gpt_researcher/context/lexical.py::rank_written_sections` 改造：保留上游分块、BM25 相对得分筛选思路，分词改为本项目中文分词，并缩短输出；其结果仅供行文衔接，不能作为项目事实依据。长报告按标题分组及节点持久化是本项目适配，并非直接运行上游 `DetailedReport`。

## 2026-11-20 原版写作对照

已在隔离的 `.venv-researcher` 安装 PyPI `gpt-researcher==0.17.0`，实际调用原版 `actions.report_generation.generate_report` 和默认 PromptFamily，未修改其正文生成逻辑。工作台仍使用原 `.venv`。对照使用相同 DeepSeek Pro 和固定真实证据，不运行上游联网研究、解析、MCP 或完整 DetailedReport。原始输入、输出及指标在 `outputs/researcher同输入对照-2026-11-19/`；目录日期保留为实验启动日期。

对照显示结构表达值得参考，但默认提示中的延长篇幅、生成参考链接等行为需要适配：原始概况输出出现 example.com 虚构引用。未将该输出直接导入项目报告，也未宣称整套上游已接入生产。

## 2026-11-26 公共资料联网发现

`safety_report/public_research.py` 参考上游 `retrievers/duckduckgo/duckduckgo.py` 的检索结果归一化方式，直接依赖同一开源搜索包 DDGS（开发验证9.16.1），不直接加载上游完整研究Agent。网页正文直接使用 trafilatura（开发验证2.4.0）。公共主题推荐、更新候选、政府来源限定、下载缓存、来源指纹、现有知识库待审核导入和操作界面为业务集成代码。本轮没有启用上游全套爬虫、深度研究或自动法规适用性认定。
