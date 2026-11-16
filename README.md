# AI Company Radar

**自动采集 AI 公司公开信息，用证据回答检索问题。**

[![Tests](https://github.com/Chenxiao-Tian/Data_Collection/actions/workflows/tests.yml/badge.svg)](https://github.com/Chenxiao-Tian/Data_Collection/actions/workflows/tests.yml)
[![Collection](https://github.com/Chenxiao-Tian/Data_Collection/actions/workflows/ai-radar.yml/badge.svg)](https://github.com/Chenxiao-Tian/Data_Collection/actions/workflows/ai-radar.yml)

[最新公司清单](https://github.com/Chenxiao-Tian/Data_Collection/tree/ai-radar-data) · [采集运行与下载](https://github.com/Chenxiao-Tian/Data_Collection/actions/workflows/ai-radar.yml) · [公司跟踪清单](config/companies.json) · [设计与边界](docs/radar_design.md)

这个版本将原来的特征收集范例升级为一个可以运行、定时更新、搜索和核查的公司资料系统。它不宣称“全球最准确”：当前没有经过外部公司情报基准评测，来源也可能错误或过时。系统的目标是让每个结果有出处，让不确定性可以看见。

## 已实现

| 能力 | 行为 |
|---|---|
| 官网采集 | 读取 HTML、meta 描述和匹配官网域名的 Organization JSON-LD；沿官网 about/company/news/research/careers 等链接扩展，默认每家公司最多 3 页 |
| 公司发现 | 从 Wikidata 的 AI 行业标签和官网地址发现线索；进入 `needs_review` 队列，不自动认定为真实 AI 公司 |
| 实体核对 | Wikidata 实体必须与登记官网域名精确匹配且唯一，不能仅按名字相同合并 |
| 结构化证据 | 公司自述、法定名称、成立日期等实际取得的字段有来源、提取方式和检查时间；未取得的融资、估值等字段明确为未知 |
| 混合检索 | SQLite FTS5 BM25 + 词项匹配 + Reciprocal Rank Fusion；内置常用中文研究词到英文词的扩展 |
| 可选语义检索 | 可显式启用本地 sentence-transformers 多语言向量检索，与关键词结果融合；默认未下载、未开启 |
| 冲突与新鲜度 | 不同字段值保留证据；30 天未检查标记 stale；同一家公司及其 Wikidata 摘要不作为多个独立来源计数 |
| 更新与追溯 | 内容哈希去重、首次见到/内容变更/最后检查时间分离，保留字段变更历史；页面删除或失败不会把旧资料清零 |
| 界面与导出 | 中文响应式仪表盘、公司详情、来源引用、筛选、分页、待核验队列、失败原因、CSV/JSON |
| 自动运行 | GitHub Actions 每天 07:23 UTC，支持手动运行；数据库 artifact 保存 90 天，最新摘要另存 `ai-radar-data` 分支 |

初始清单为 **16 家公司**。人工方向标签仅用于筛选，不等同于采集确认的事实。新增公司时编辑 `config/companies.json`，无需写代码。

## 直接使用

1. 打开 [AI Company Radar Actions](https://github.com/Chenxiao-Tian/Data_Collection/actions/workflows/ai-radar.yml)，选择最近一次运行。
2. 查看运行 Summary 的成功/失败统计。下载 **`ai-company-radar`** artifact，解压后打开 `index.html`，即可离线搜索、筛选、查看引用和导出 CSV。
3. 浏览 [ai-radar-data 分支](https://github.com/Chenxiao-Tian/Data_Collection/tree/ai-radar-data) 读取最新清单、JSON 或下载 HTML。

离线 HTML 检索的是导出的档案、摘要和引用；完整网页文本检索需要下面的本地服务。GitHub 仓库文件预览不会执行 HTML。当前没有为此项目启用 GitHub Pages 或公共服务器。

## 本地运行（Python 3.10+）

新采集器和网页服务本身仅使用 Python 标准库，不需要付费 API 密钥。

```bash
git clone https://github.com/Chenxiao-Tian/Data_Collection.git
cd Data_Collection
export PYTHONPATH=src

# 采集并自动发现候选公司
python -m ai_radar collect
# 检索原文，有来源和时间
python -m ai_radar search "开源推理"
# 中文网页界面，只监听本机
python -m ai_radar serve --port 8080
# 导出独立 HTML、JSON、CSV
python -m ai_radar export --out radar-output
# 查看运行状态
python -m ai_radar status
```

浏览器打开 `http://127.0.0.1:8080`。支持只读 API：`GET /api/companies`、`GET /api/search?q=inference` 和 `GET /health`。不提供远程任意 URL 抓取接口。

也可以 `pip install -e .` 后使用 `ai-radar` 命令；此安装会同时装入旧版特征导出依赖。Windows PowerShell 设置源路径用 `$env:PYTHONPATH="src"`。

### 可选本地多语言向量检索

```bash
pip install -e '.[semantic]'
ai-radar search '语音合成' --semantic-model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

首次会下载模型权重并需要额外内存；文本在本地编码，不调用付费模型 API。模型启用是显式选择；默认 GitHub 定时采集和网页 API 使用 BM25 + 词项融合。向量检索未经实网端到端验收，不应将安装选项当成已运行服务。

## 扩展公司清单

```json
{
  "id": "example-ai",
  "name": "Example AI",
  "website": "https://company.example/",
  "aliases": ["公司中文名"],
  "tags": ["语音"],
  "pages": ["https://company.example/about"],
  "wikidata": true
}
```

这是格式示例，不是真实公司。`pages` 优先于自动发现的官网子页。跨域改名/迁站需人工核实后修改官网；不要将目录网站、产品名、实验室或同名实体直接当成公司。

## 准确性约束

- 不用 LLM 生成事实或填补融资、营收、员工数量；官网营销文案标为“官网自述”。
- 单一来源、冲突、过期与未知分别展示；排名分数是检索相关性，**不是正确率或投资评分**。
- 多来源支持只说明来源组一致，不构成保证。默认采集来源不会自动获得“独立交叉核验”状态。
- 发现覆盖依赖 Wikidata 行业标注，不等于全网所有公司。付费数据库、搜索引擎付费 API、动态网页渲染、登录站点和完整融资数据库尚未接入。
- robots.txt 授权不明、反爬页面、非公开 IP、过大响应和跨域跳转会拒绝；错误写入状态报告，不伪造成功。
- 检查时间不是发布日期。页面可访问不意味着全部内容最新；过去抓到的事实在失败后保留旧时间戳。

## 运维

工作流在推送代码或清单后触发，也可以在 Actions 页面手动运行。定时为 07:23 UTC（纽约冬令时 02:23，夏令时 03:23），GitHub 调度可能延迟；长期无活动可能停用计划任务。源站不可达时会保留此前证据并记录失败，完全无成功来源时工作流失败。

数据库由上一份未过期 `radar-database` artifact 恢复。恢复失败时任务停止，避免用空库覆盖已有状态。超过 90 天没有成功上传，完整文本/历史可能需要重新采集；`ai-radar-data` 的摘要仍有 Git 版本历史。建议定期下载数据库做独立备份。

GitHub Actions 是否计费以账号额度及平台政策为准；系统不申请或购买第三方付费服务。公开仓库的 artifact、数据分支与代码均应视为公开资料，不写入私密业务资料或凭证。

## 测试和旧代码

```bash
python -m pip install pytest==8.4.2
PYTHONPATH=src python -m pytest -q
python -m compileall -q src scripts tests
```

测试包含幂等更新、冲突保留、来源独立性、过期信息、未知字段、同名实体隔离、检索注入、脚本注入、SSRF 地址拒绝和离线采集到检索的完整流程。测试 fixture 不是生产数据。

`src/data_collection/` 和 `scripts/collect_features.py` 保留旧接口；修复了合并残留导致的语法错误、HTTP 参数编码/缓存与部分缺失值语义。旧版 SSFF 的启发式分数和第三方适配器未经全面验证，**不进入新 Radar 的事实数据库或定时任务**。历史说明保存在 [legacy_collector.md](docs/legacy_collector.md)。
