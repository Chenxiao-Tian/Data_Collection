# Scam AI 数据整理指引

本指引复现 `sample_data/startup_profile.json` 中的字段来源、人工校验流程与在管道中的使用方式，确保所有信息均可追溯到可靠的公开渠道。

## 1. 目标概览

- **CompanyName**: Scam AI
- **Sector**: AI anti-fraud（深度伪造 / 语音克隆识别与风险评分）
- **ProductType**: SaaS/API，面向身份与内容真实性校验场景
- **时间戳**: 2025-10-28（UTC），表示资料整理的观察窗口

## 2. 数据来源

| 信息块 | 具体字段 | 公开来源 | 说明 |
| --- | --- | --- | --- |
| 公司介绍 | 公司定位、产品形态、风险提示 | [Scam AI 官方网站](https://www.scam.ai/) | 网站首页与产品介绍中明确强调 AI 反诈骗、深度伪造检测及 API 交付方式 |
| 创始人履历 | Ben (Simiao) Ren 背景 | [Ben Ren LinkedIn](https://www.linkedin.com/in/simiao-ben-ren/) | 履历显示 Meta 高级研究科学家经历、生成式模型与视觉/音频 ML 专长、博士学历 |
| 创始人履历 | Dennis Ng T. Sang 背景 | [Dennis Ng T. Sang LinkedIn](https://www.linkedin.com/in/dennisngtsang/) | 履历显示曾任 Sportsync.com 创始工程师，负责前端、UX 和产品交付 |
| 市场规模 | `market.size_usd`、`market.cagr` | MarketsandMarkets《Identity Verification Market》公开摘要（2023） | 摘要中披露身份验证市场将于 2022–2027 期间从 106 亿美元增至 218 亿美元，复合增速 15.6% |

> 若外部报告链接需登录，可在搜索引擎使用关键词 `"Identity Verification Market" MarketsandMarkets 2023 15.6%` 获取公开版摘要。

## 3. 字段映射与整理

1. `profile`
   - `name` 与 `domain` 直接来自官方站点标题与 URL。
   - `industry` 归类为 "AI anti-fraud"，与网站宣称的深度伪造与语音克隆检测一致。
   - `market_size`、`market_growth_rate` 等若无可靠公开数据，则保持 `Unknown`/`null`，避免主观推断。

2. `product`
   - `frontier_tech_usage` 设为 `Emphasized`，因为官网多次强调使用先进 AI/LLM 模型。
   - 无公开留存或点评数据，因此 `pmf`、`reviews` 均标记 `Unknown`。

3. `founders`
   - `education_level`、`school_tier`：根据 LinkedIn 的学历信息，博士与顶尖院校视为 Tier-1，本科来自区域性院校标记为 Tier-2。
   - `leadership_experience`：对担任 "Senior Research Scientist" 或 "Founding Engineer" 的经历记为 `true`。
   - `top_company_experience`：Meta 属于顶级科技企业，标记 `true`；Sportsync.com 为创业公司，标记 `false`。
   - `role_alignment`：依据履历与产品方向的贴合度进行 0–1 区间的人工评分，用于 FIFS 计算。

4. `knowledge`
   - `founder_team_complementarity`、`prior_signals`、`potential_risks` 均通过阅读官网与 LinkedIn 资料人工总结。
   - `data_gaps` 明确列出在公开渠道无法确认的字段，作为后续尽调清单。
   - `timestamp_utc` 使用 ISO 8601，方便和其他观测点合并。

## 4. 校验流程

1. 打开上述三个公开链接，核对字段描述与时间戳。
2. 将关键信息记录在电子表格或笔记中，确保引用原文措辞或实证事实。
3. 对于市场规模数值，保存报告摘要的截图或引用原文，确保数字来自可查证的来源。
4. 将整理好的数据输入到 `sample_data/startup_profile.json`，保持 JSON 结构与现有字段一致。
5. 使用 `jq` 或在线 JSON 校验器确认语法正确。

## 5. 在项目中的使用

若 `.env` 中已配置 SerpAPI / Crunchbase / NewsAPI / Product Hunt / Proxycurl / OpenCorporates 等密钥，仅需输入公司名称即可自动抓取：

```bash
python scripts/collect_features.py "Scam AI" --output-dir outputs/scam_ai
```

若缺少部分密钥，可叠加 `--profile-path sample_data/startup_profile.json` 作为离线补充，程序会自动将实时抓取与手工整理的字段合并。

执行后会生成：

- `features_ssff.parquet`：分类特征（若实时 API 返回完整市场数据则自动覆盖离线缺口）。
- `features_founder.parquet`：创始人分层（Ren 与 Ng 的 FIFS 平均得分约 0.885，若 Proxycurl 返回最新履历则会动态更新）。
- `features_external.json`：除市场量化指标外，还包含 `knowledge` 中的补充说明、风险、数据缺口以及引用的公开链接。

## 6. 后续扩展建议

- 接入 SERP/API 获取实时舆情后，可更新 `sentiment.average` 与 `potential_risks`。
- 若未来披露融资或合规证书，可直接补充 `funding`、`compliance` 字段，并重新运行管道生成最新快照。

通过上述步骤即可透明复现 Scam AI 的资料采集过程，并确保所有字段均指向可信的公开来源。
