# AI Startup Feature Collector

该仓库提供了一个面向研究者与投资分析的开源范例工程，演示如何沿用论文中提出的 **Startup Success Feature Framework (SSFF)**，自动化收集 AI 创业公司的结构化特征。项目通过模块化的数据源接入层、特征抽取层与 CLI 工具，帮助你快速构建预测模型（Random Forest、神经网络等）所需的 `Prediction Block`、`Founder Segmentation Block` 以及 `External Knowledge Block` 特征表。

## 功能概览

- ✅ **Prediction Block**：聚合产品、市场、融资、执行力等 14 类分类特征，输出到 `features_ssff.parquet`。
- ✅ **Founder Segmentation Block**：依据教育背景、领导力、过往创业经验和“Founder-Idea Fit (FIFS)” 得分，输出创始人分层指标到 `features_founder.parquet`。
- ✅ **External Knowledge Block**：整合 SERP / 市场报告 / 舆情等扩展信号，生成 `features_external.json`。
- ✅ **开放数据接入**：内置 `OpenDataSource` 会并行请求 SerpAPI、Crunchbase、NewsAPI、Product Hunt、OpenCorporates、Proxycurl 等可靠公开渠道；通过 `.env` 注入 API 凭证后，仅输入创业公司名称即可自动抓取并落地特征。
- ✅ **Typer CLI**：`scripts/collect_features.py` 提供一键收集命令，可输出特征并打印 JSON。
- ✅ **Pytest 用例**：`tests/test_pipeline.py` 验证三大特征模块的核心逻辑。

## 快速上手

```bash
# 1. 安装依赖
pip install -e .[test]

# 2. 在仓库根目录创建 .env，填入所需 API 凭证（任意缺失的服务将自动跳过）
cat <<'ENV' > .env
SERPAPI_KEY=your_serpapi_key
CRUNCHBASE_KEY=your_crunchbase_user_key
NEWSAPI_KEY=your_newsapi_key
PRODUCTHUNT_TOKEN=your_producthunt_token
PROXYCURL_API_KEY=your_proxycurl_key
OPENCORPORATES_APP_TOKEN=optional_opencorporates_token
ENV

# 3. 输入公司名称，自动全网抓取（示例：Scam AI）
python scripts/collect_features.py "Scam AI" --output-dir outputs/scam_ai

# 4. 查看结果
ls outputs/scam_ai
parquet-tools show outputs/scam_ai/features_ssff.parquet
cat outputs/scam_ai/features_external.json

# 5. 运行测试
pytest
```

运行完毕后，可在 `outputs/scam_ai/` 中找到三份特征文件：

- `features_ssff.parquet`：14 个分类特征，可直接喂给分类模型。
- `features_founder.parquet`：创始人分层 & FIFS 指标。
- `features_external.json`：市场规模、CAGR、竞争格局、舆情与基于公开资料整理的知识摘要（公司概况、创始人履历、风险、数据缺口等），并附带 API 来源链接。

## 项目结构

```
├── pyproject.toml                # 项目元数据与依赖
├── README.md                     # 当前文档
├── sample_data/                  # 示范数据（可替换为真实抓取结果）
│   └── startup_profile.json
├── scripts/
│   └── collect_features.py       # Typer CLI，负责命令行调用
├── src/
│   └── data_collection/
│       ├── config.py             # 环境变量加载与运行配置
│       ├── http.py               # 轻量 HTTP 客户端 + 缓存
│       ├── pipeline.py           # 管道编排、落盘逻辑
│       ├── utils.py              # 通用工具函数
│       ├── features/             # 特征抽取模块
│       │   ├── base.py
│       │   ├── prediction.py
│       │   ├── founder.py
│       │   └── external.py
│       └── sources/              # 数据源封装
│           ├── base.py
│           └── open_data.py
 └── tests/
    └── test_pipeline.py          # 单元测试
```

### 支持的 API 凭证

| 环境变量 | 用途 | 备注 |
| --- | --- | --- |
| `SERPAPI_KEY` | 通过 Google Search 提取官网、简介、招聘信号 | [SerpAPI](https://serpapi.com/) 用户密钥 |
| `CRUNCHBASE_KEY` | 获取融资、创始人和竞争格局 | Crunchbase `user_key` |
| `NEWSAPI_KEY` | 收集新闻舆情并计算情绪分值 | [NewsAPI](https://newsapi.org/) |
| `PRODUCTHUNT_TOKEN` | GraphQL 查询 Product Hunt 投票、评论、评分 | 需要 `Developer Token` |
| `PROXYCURL_API_KEY` | 解析创始人 LinkedIn 履历，补充 FIFS 特征 | [Proxycurl](https://nubela.co/proxycurl) |
| `OPENCORPORATES_APP_TOKEN` | 查询注册号、成立日期等合规字段 | 可选，OpenCorporates 免费 token |

任意密钥缺失时，对应模块将自动跳过并返回 `Unknown`，但不会阻断整体流程。

## 扩展与定制

1. **替换数据源**：继承 `DataSource`，在 `pipeline.run_from_config` 中注入自定义的可信渠道（如 PitchBook、Tracxn、Dealroom）。
2. **引入 RAG 信号**：在 `OpenDataSource` 中新增 `async def _rag_signals()`，调用 SERP API + LLM，总结后写入 `payload["external_rag_summary"]`。
3. **增强 Founder-Idea Fit**：在 `FounderFeatureBlock` 中，接入 `text-embedding-3-large` 的余弦相似度，将结果归一化到 [-1, 1]，并记录成功 / 失败样本。
4. **模型训练**：将 `features_ssff.parquet` 与 `features_external.json` 读入 Pandas DataFrame，结合历史标签训练随机森林或神经网络。

欢迎根据实际需求扩展此仓库，构建更全面的 AI startup 数据资产。

## Scam AI 实战数据说明

- 默认命令会实时访问上述 API，若某些密钥缺失，可使用 `--profile-path sample_data/startup_profile.json` 注入离线快照进行演示。
- 所有事实均来自官方站点与创始人 LinkedIn 页面，详细整理过程、字段解释与校验步骤见 [`docs/scam_ai_collection.md`](docs/scam_ai_collection.md)。
- 运行示例命令即可在 `features_external.json` 中看到实时抓取的市场指标与知识摘要，并自动合并离线补充数据。
