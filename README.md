# Miko Atelier | 视觉笔记 V1

无需前端构建工具的摄影学习网站。每天自动添加约 8 张摄影/电影美术图片，为每张图片生成可展开的摄影学习卡片，并提供私人收藏与笔记。

## 状态

- ✅ 首页、筛选、画廊、作品详情、默认折叠的学习卡片。
- ✅ 本地收藏、笔记、本机照片上传（IndexedDB，**仅在当前浏览器**）。
- ✅ GitHub Actions 每日定时运行，自动从 Wikimedia Commons 搜集符合可复用授权条件的作品，记录作者/许可/原始链接，去重。
- ✅ 可选 Gemini 免费视觉 API 分析；没有密钥时仍可每日更新图片，解析显示为待生成。
- ⏳ 需要部署至你自己的 GitHub 仓库、启用 Pages，并根据你的 Gemini AI Studio 帐号实际配额设置 API Key。当前并未发布上线。
- ⏳ Instagram 等非开放平台图片的跨设备同步、私人照片自动 AI 解析，需要未来安全后端和更详细授权设计，此版不自动上传。

## 零额外费用原则

1. 站点为纯静态 HTML/CSS/JS，不依赖付费托管。
2. Github Actions 默认 Linux runner，通常适合个人项目免费额度；注意遵守你账号实际使用条款。
3. **没有 Gemini API Key 时不会调用 AI**；即使有 Key，遇到 API 额度错误也会跳过，不会自动切换到收费服务。你仍需在 Google AI Studio **确认自己项目的模型和免费配额**，避免主动开通付费结算。
4. 官方 Gemini 免费层可能将数据用于改进服务。本站只向 Gemini 发送开放授权图库缩略图（如配置 Key），**从不自动上传私人照片**。

## 本地预览

```bash
cd miko-visual-journal
python3 -m http.server 8080
# 打开 http://localhost:8080
```

已于 2026-10-20 实测并收录首批 8 张开放授权作品：4 张人像、3 张其他摄影、1 张电影美术，图片地址逐一验证可读取。未配置任何 API Key。

## 收集第一批内容

```bash
python3 scripts/daily.py --dry-run   # 先从开放图库检查候选及许可证，不保存
python3 scripts/daily.py             # 正式保存当天 8 张新作品
```

此操作要求联网，访问 Wikimedia Commons；如果 API 请求失败，保留现有内容，不会自动填充不可靠来源。默认对每张图片保留作者名、许可类型、作品原网页；授权元数据仍应在重要使用前复核。电影美术来源较少时，其他摄影会自动补齐，而不是硬凑 20%。

## 让 Gemini 自动生成学习卡片

1. 在 [Google AI Studio](https://aistudio.google.com/) 建立仅使用 Free Tier 的 API 密钥。**不要把密钥写进代码或发给别人。**
2. 经用户单独确认后，在 GitHub 仓库 Settings → Secrets and variables → Actions → New repository secret，新建 `GEMINI_API_KEY`。不要在聊天中发送 Key。
3. 只有在确认此 Google 项目**未关联结算账号**、模型免费额度可用、并同意开放图库缩略图发送给 Google 后，才将仓库变量 `GEMINI_FREE_TIER_CONFIRMED` 设为 `true`。未设定时，即使存在密钥也不会调用 AI。脚本无法替你验证 Google 项目结算状态，开关本身不是费用上限。
4. 可选新增 `WIKIMEDIA_USER_AGENT`，建议设为包含有效联系信息的自定义 User-Agent（遵循 Wikimedia API etiquette）。
5. Workflow 采用 `gemini-3.1-flash-lite`，如果你的实际免费项目不支持这个模型，就在 `.github/workflows/daily.yml` 中改为账户中可免费调用的视觉模型。**不可使用付费模型做自动回退。**
6. 手动运行 Actions → Daily Visual Edit → Run workflow 验证，然后按 UTC 定时运行。

**注意**：上传的私人照片只存在你的设备上，不会被自动发送给 Gemini。打开私人照片详情，可复制提示词，在 ChatGPT 中自行附图分析，再把四个字段的 JSON 粘贴回学习卡片；这个流程不需要 API Key。

## 在 GitHub Pages 发布

1. 创建一个仓库，上传此项目所有文件（包括 `.github/workflows/daily.yml`）。
2. Settings → Pages → Build and deployment → **GitHub Actions**（不是 Deploy from a branch）。
3. Actions → Daily Visual Edit → Run workflow，检查 `curate`、`deploy-pages` 步骤；同一个 workflow 会自动发布更新后的页面。
4. Pages 的网页可公开访问，**不是真正的私人网站**。默认只公开有来源与许可信息的开放图库作品，私人收藏和笔记在浏览器本地保存。

## 关于 Unsplash

原始规划涉及 Unsplash，但它的官方 [API guidelines](https://help.unsplash.com/en/articles/2511245-unsplash-api-guidelines) 明确提及 non-automated, high-quality experiences 和反对 data mining。因为你要求每天无人值守自动收图，V1 **没有使用 Unsplash API 自动批量抓取**，先用 Wikimedia Commons 开放授权图库完成自动化验证。将来若取得适合该使用方式的授权或得到官方确认，可作为可选来源接入。

## 一些技术限制

- 图片来自 Wikimedia Commons 热链缩略图；个别来源图可能失效，必要时清理坏链接。
- 大量作品长期累计会增加 JSON 文件尺寸；后续可分页归档。
- 本地收藏与上传照片不跨设备同步，浏览器清理缓存可能丢失；「完整备份收藏和照片」包含原图、笔记、学习卡片和收藏索引，可通过「恢复备份」导入。备份包含私人内容，请勿放入公开仓库。
- 仅凭分辨率无法完全判断摄影审美质量。后续可加入可解释的推荐评分，但不应未经证实地捏造拍摄信息。
- Gemini 的分析只是图像观察和推测，不等同于原作者的真实创作说明。

## 文件概览

- `index.html` 页面结构
- `assets/styles.css` 视觉设计
- `assets/app.js` 收藏、筛选、详情、笔记、本机照片上传
- `scripts/daily.py` 免费开放图库收集与可选 Gemini 分析
- `.github/workflows/daily.yml` 定时任务
- `data/entries.json` 作品数据（首次运行前为空）

## 本次修复与验证

- 以北京时间日期计算每天上限；当天重跑仅补齐缺额，避免重复收图。
- 图片下载头验证失败则跳过；保留完整作者署名，页面显示作者、许可与来源。
- 学习卡片默认隐藏，笔记立即保存，修复切换作品时延迟保存串写风险。
- 私人上传支持手动分析结果导入、完整备份与合并恢复，均不写入公开数据。
- AI 必须同时有 Key 与明确免费层确认；额度或权限错误即停，不切换模型。
- GitHub Actions 仅在公开仓库运行标准 Ubuntu runner；Pages artifact 保留 1 天。
- `Publish Miko Atelier` 负责网站变更发布；`Daily Visual Edit` 每天北京时间 04:17 收集并发布，GitHub 定时任务可能延迟。
- 每次收图最多分析 8 张缺失卡片，可在以后启用 AI 时补齐已有作品。
- `python scripts/test_daily.py` 覆盖每日上限、补齐去重、许可拒绝、dry-run 不写文件不调用 AI、未确认时 AI 禁用。

## 免费服务依据（核查于 2026-10-20）

- [GitHub Actions 计费](https://docs.github.com/en/billing/concepts/product-billing/github-actions)：公开仓库的标准 GitHub runner 免费。
- [Gemini API 定价](https://ai.google.dev/gemini-api/docs/pricing)：gemini-3.1-flash-lite 的 Free Tier 支持图片输入；账户实际配额、区域和结算状态需要在用户自己的 AI Studio 核实。
- [Wikimedia 复用指南](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia)：按每张作品具体许可保留署名及许可链接。

此静态版本不提供账号登录和跨设备私人同步。来源自动筛选不等同于人工审美编辑，也不保证每天图库服务可用或一定补足 8 张；页面会显示真实状态。
