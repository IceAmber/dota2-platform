# DOTA2 国服社区平台

> 纯静态、零后端、零构建工具的 DOTA2 国服社区网站骨架。
> 为 DOTA2 国服新玩家提供 **新手指引** + **版本阵容周报**，数据来自 OpenDota 免费 API。
> 社区公益项目，非商业用途，部署于 GitHub Pages，零成本。

---

## ✨ 特性

- **纯静态**：HTML + CSS + 原生 JS，无框架、无构建工具、无外部 CDN 脚本依赖。
- **中文内容**：全站中文，英雄名为国服官方中文名。
- **移动端适配**：深色电竞风 + 响应式布局，手机上也能舒服地看榜单。
- **数据自动刷新**：`scripts/fetch_hero_data.py` 用标准库 `urllib` 抓取 OpenDota，
  生成 `site/data/herostats.json`，页面用 JS 读取渲染。
- **容错**：抓取失败时保留上一次数据，站点永不因数据源故障而空白。

---

## 📁 文件结构

```
dota2-platform/
├── site/                     # 静态站根目录（即 GitHub Pages 发布目录）
│   ├── index.html            # 首页：定位 + 导航 + 最新周报摘要
│   ├── guide.html            # 新手指引：分步注册 / 排查表 / 新手英雄
│   ├── report.html           # 版本周报：三榜单 + 认知差区块（读 JSON 渲染）
│   ├── about.html            # 关于 / 免责声明
│   ├── css/style.css         # 全站样式（深色电竞风，响应式）
│   ├── js/main.js            # 原生 JS：读取 JSON、渲染榜单、通用交互
│   └── data/
│       ├── herostats.json    # 由脚本生成的英雄数据（勿手改）
│       └── weekly_report.md  # --markdown 可选生成的周报文本
└── scripts/
    └── fetch_hero_data.py    # 数据刷新脚本（仅标准库）
```

---

## 🚀 快速开始

### 1. 生成数据（需要联网）

```bash
cd dota2-platform
python3 scripts/fetch_hero_data.py          # 生成 site/data/herostats.json
python3 scripts/fetch_hero_data.py --markdown   # 额外生成周报 markdown
```

> 失败时脚本会打印友好错误并**保留上一次的数据**，不会破坏站点。

### 2. 本地预览

由于浏览器禁止 `file://` 直接读取本地 JSON，请用本地静态服务器预览：

```bash
cd site
python3 -m http.server 8080
# 浏览器访问 http://localhost:8080
```

---

## 📤 部署到 GitHub Pages

1. 在 GitHub 新建仓库（如 `dota2-platform`），把整个项目推送上去：

   ```bash
   git init
   git add .
   git commit -m "init: dota2 国服社区静态站"
   git branch -M main
   git remote add origin git@github.com:<你的用户名>/dota2-platform.git
   git push -u origin main
   ```

2. 打开仓库 **Settings → Pages**：

   - **Source** 选择 `Deploy from a branch`
   - **Branch** 选择 `main`，目录选 **`/site`**（只发布静态站目录）
   - 保存后等待 1~2 分钟，站点会出现在
     `https://<你的用户名>.github.io/dota2-platform/`

3. 之后每次更新 `site/data/herostats.json` 并 push，站点即自动更新。

> 提示：`/site` 里的相对路径（`css/`、`js/`、`data/`）在 GitHub Pages 项目子路径下也能正常工作。

---

## ⏰ 定时刷新（cron）

把抓取脚本加入 cron，即可做到「每日自动更新周报」：

```bash
crontab -e
```

示例（每天 08:03 抓取并生成周报）：

```
3 8 * * *  cd /home/iceamber/.openclaw/workspace/dota2-platform && /usr/bin/python3 scripts/fetch_hero_data.py --markdown >> cron.log 2>&1
```

**注意**：cron 抓到的数据在你本机，GitHub Pages 用的是仓库里的那份。
要让线上更新，需要把生成的 `site/data/herostats.json` 提交并 push。常见做法：

- **方案 A（最省事）**：写一个小脚本 `cron` 里执行 —— 抓取 → `git add site/data/` → `git commit` → `git push`（建议用带写权限的 PAT 或 SSH key）。
- **方案 B（免 push）**：改用 GitHub Actions 定时任务（见下）。

### GitHub Actions 自动刷新（推荐，全托管）

在仓库建 `.github/workflows/refresh-data.yml`：

```yaml
name: refresh-data
on:
  schedule:
    - cron: '23 0 * * *'   # 每天 UTC 00:23（约北京时间 08:23）
  workflow_dispatch:        # 支持手动触发

jobs:
  refresh:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: 拉取数据
        run: python3 scripts/fetch_hero_data.py
      - name: 提交更新
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add site/data/
          git diff --cached --quiet || git commit -m "chore(data): refresh hero stats"
          git push
```

> 这样数据每天自动更新、自动部署，全程零成本零人工。

---

## 📊 herostats.json 结构（节选）

```json
{
  "generated_at": "2026-08-18T22:41:56+08:00",
  "data_date": "2026-08-18",
  "source_url": "https://api.opendota.com/api/heroStats",
  "total_pub_picks": 41039784,
  "heroes": [
    {
      "id": 42,
      "name": "骷髅王",
      "name_en": "Wraith King",
      "img": "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/skeleton_king.png",
      "pub_pick": 490437,
      "pub_win": 268614,
      "pub_winrate": 54.77,
      "pub_ban": 0,
      "pro_pick": 0,
      "pro_win": 0,
      "pro_winrate": null,
      "pro_ban": 0,
      "pick_share_pct": 1.196,
      "pick_rank": 18,
      "winrate_rank": 1,
      "pro_rank": null,
      "is_gap": false
    }
  ],
  "gap_ids": [76, 92, 32],
  "summary": { "total_heroes": 127, "gap_count": 11, "pro_sample_heroes": 107 }
}
```

- `pub_winrate`：路人胜率 = 胜场/出场 × 100（保留 2 位）；`pro_winrate` 同理（职业）。
- `pick_rank` / `winrate_rank`：按出场/胜率降序的排名。
- `is_gap` + `gap_ids`：「认知差」——胜率排名 ≤25 且出场排名 ≥50 的英雄。
- 胜率榜只统计出场 ≥5000 场的英雄（`min_pub_pick` 可调），避免小样本噪声。

---

## ⚠️ API 限流说明

OpenDota 免费层约为 **60 次/分、3000 次/天/IP**。

- 本脚本每次运行只发 **1 次**请求（失败最多重试 3 次并退避），
  一天 1~2 次刷新远低于限额，正常使用不会触发限流。
- 脚本内置超时（25s）与重试退避；请求带正常 `User-Agent`，尊重 API 提供方。
- 如需更高的频率，请考虑自建代理或申请 OpenDota 开发者支持。

---

## 📄 免责声明

- 本站为 **社区公益项目**，非官方、非商业，与 Valve / 完美世界无关。
- 数据为抓取时点快照，胜率随版本与时间波动，榜单仅供参考，不构成游戏建议。
- 新手指引整理自公开资料，官方流程如有变动请以官方最新公告为准。

---

## 🤝 一起参与

欢迎内容校对、页面改进、数据可视化建议。请提 Issue / PR，一起把国服 DOTA2 新手生态做好。
