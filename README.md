# AI Startup Feature Collector

该仓库提供了一个面向研究者与投资分析的开源范例工程，演示如何沿用论文中提出的 **Startup Success Feature Framework (SSFF)**，自动化收集 AI 创业公司的结构化特征。项目通过模块化的数据源接入层、特征抽取层与 CLI 工具，帮助你快速构建预测模型（Random Forest、神经网络等）所需的 `Prediction Block`、`Founder Segmentation Block` 以及 `External Knowledge Block` 特征表。

## 功能概览

- ✅ **Prediction Block**：聚合产品、市场、融资、执行力等 14 类分类特征，输出到 `features_ssff.parquet`。
- ✅ **Founder Segmentation Block**：依据教育背景、领导力、过往创业经验和“Founder-Idea Fit (FIFS)” 得分，输出创始人分层指标到 `features_founder.parquet`。
- ✅ **External Knowledge Block**：整合 SERP / 市场报告 / 舆情等扩展信号，生成 `features_external.json`。
- ✅ **开放数据接入**：默认使用 `OpenDataSource` 模拟接入 Product Hunt、Crunchbase、市场报告等开放数据源，方便在无密钥环境中演示；支持通过 `.env` 注入真实 API 凭证后替换为生产级连接器。
- ✅ **Typer CLI**：`scripts/collect_features.py` 提供一键收集命令，可输出特征并打印 JSON。
- ✅ **Pytest 用例**：`tests/test_pipeline.py` 验证三大特征模块的核心逻辑。

## 快速上手

```bash
# 1. 安装依赖
pip install -e .[test]

# 2. 使用样例数据收集特征
python scripts/collect_features.py \
  --profile-path sample_data/startup_profile.json \
  --name "SynthPilot" \
  --domain "synthpilot.ai" \
  --industry "AI" \
  --stage "Series A" \
  --region "US" \
  --output-dir outputs/demo

# 3. 查看结果
ls outputs/demo
parquet-tools show outputs/demo/features_ssff.parquet
cat outputs/demo/features_external.json

# 4. 运行测试
pytest
```

运行完毕后，可在 `outputs/demo/` 中找到三份特征文件：

- `features_ssff.parquet`：14 个分类特征，可直接喂给分类模型。
- `features_founder.parquet`：创始人分层 & FIFS 指标。
- `features_external.json`：市场规模、CAGR、竞争格局、舆情等扩展信号。

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

## 扩展与定制

1. **替换数据源**：继承 `DataSource`，在 `pipeline.run_from_config` 中注入真实的 Product Hunt / Crunchbase / News API 适配器即可。
2. **引入 RAG 信号**：在 `OpenDataSource` 中新增 `async def _rag_signals()`，调用 SERP API + LLM，总结后写入 `payload["external_rag_summary"]`。
3. **增强 Founder-Idea Fit**：在 `FounderFeatureBlock` 中，接入 `text-embedding-3-large` 的余弦相似度，将结果归一化到 [-1, 1]，并记录成功 / 失败样本。
4. **模型训练**：将 `features_ssff.parquet` 与 `features_external.json` 读入 Pandas DataFrame，结合历史标签训练随机森林或神经网络。

欢迎根据实际需求扩展此仓库，构建更全面的 AI startup 数据资产。
