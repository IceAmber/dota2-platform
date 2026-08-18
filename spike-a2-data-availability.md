# Spike A2：数据可得性验证报告

> 验证日期：2026-08-17（UTC）
> 验证方式：对 OpenDota API 的**实际 curl 调用** + 公开资料调研
> 结论先行：**"实时观战辅助"需降级为"准实时赛况速览"**，其余（赛后复盘、版本追踪、英雄池）**可行**。

---

## 验证 1：OpenDota API 实际可用性 —— ✅ **可行**

### 证据（全部为本次实际调用）

**`GET https://api.opendota.com/api/heroStats`** → HTTP 200，164 KB，**127 个英雄**。
- 关键字段：`localized_name`、`pub_win` / `pub_pick`、`pub_win_trend` / `pub_pick_trend`、`pro_win` / `pro_pick` / `pro_ban`、`turbo_wins` / `turbo_picks`、`roles`、基础属性。
- 示例（按出场率排序）：Pudge pub_pick=1,117,904、胜率 51%；Lion pub_pick=1,029,753、胜率 48%；Lina pub_pick=832,680、胜率 49%。
- → 可直接支撑：**胜率榜 / 出场率榜 / 英雄池 / BP 分析（pro_pick/pro_ban）/ 版本趋势（`*_trend`）**。

**`GET https://api.opendota.com/api/proMatches`** → HTTP 200，100 场近期职业比赛。
- 含 **TI 2026（leagueid=19719）**：LGD Gaming vs Team Yandex，match_id=8948533452。

**`GET https://api.opendota.com/api/matches/8948533452`**（28 小时前的 TI 比赛，已完整解析）→ HTTP 200，**325 KB**，68 分钟比赛。
- 顶层字段：`players[10]`、`picks_bans`、`teamfights`、`objectives`、`chat`、`tower_status`、`radiant_gold_adv`（时间序列，69 个采样点）、`draft_timings`、`replay_url`、队伍信息（含 logo）。
- 单玩家字段：kills/deaths/assists、last_hits、gold_per_min、xp_per_min、level、kda、lane、hero_damage、hero_healing、tower_damage、obs_placed/sen_placed、camps_stacked。
- 注：`players[]` 无 `hero_name` 字段，需用 `hero_id` 对照 heroStats 解析（如 id=36 → Necrophos）。
- → 可直接支撑：**赛后复盘（KDA/GPM/XPM/视野/团战）、BP 还原、经济曲线、伤害数据**。

**`GET https://api.opendota.com/api/matches/{id}`（进行中/刚结束的比赛）** → 只返回**骨架**（duration=0、version=null、玩家数据全零）。见验证 3 的时效分析。

**限流**（本次实测响应头，无 API key）：
- `x-rate-limit-remaining-minute: 59`、`x-rate-limit-remaining-day: 2992`（共享池，约 60 次/分钟、3000 次/天/IP）。

---

## 验证 2：实时观战数据获取 —— ⚠️ **部分可行**（核心风险点确认）

### 结论
1. **GSI 只能拿"自己本地客户端正在运行的那一局"的数据**——要么是自己打的局，要么是客户端内正在观战的局。**不存在"通过网络订阅任意正在进行的比赛"的 GSI 能力。**
2. **职业比赛/任意玩家比赛的实时数据拿不到**（除非：a) 用自己客户端进 DotaTV 观战该场；b) 走第三方转发，见下文）。
3. **存在一条降级路径**：OpenDota 的 `/api/live` 提供**约 120 秒延迟**的准实时赛况数据，覆盖约 100 场热门比赛。

### 证据

**GSI 工作机制（社区/开源库文档一致确认）：**
- GSI = 本地 Dota 2 客户端向配置文件里指定的 URI（`gamestate_integration_*.cfg`）**主动 HTTP POST JSON 游戏状态**。数据只来自本地客户端，不是服务端可查询的 API。
- **Playing（自己打）模式**：只有本地玩家自身的数据。
- **Spectating（客户端内观战）模式**：观战局内全部玩家的数据。开源库显式区分两种模式并给出 `IsSpectating` 标志（[antonpup/Dota2GSI](https://github.com/antonpup/Dota2GSI)、[MrBean355/dota2-gsi Wiki](https://github-wiki-see.page/m/MrBean355/dota2-gsi/wiki/Library-Guide)）。
- Valve 官方 issue 证实：GSI 观战即"在客户端内观察 DotaTV 的一局比赛"，没有局外按 MatchID 拉取任意比赛的机制（[ValveSoftware/Dota2-Gameplay #27260](https://github.com/ValveSoftware/Dota2-Gameplay/issues/27260)、[#15007](https://github.com/ValveSoftware/Dota2-Gameplay/issues/15007)）。

**观战延迟（硬约束）：**
- DotaTV 标准防作弊延迟约 **2 分钟**（120 秒）；赛事方可按 Valve 政策再加至最多 15 分钟（[Liquipedia DotaTV](https://liquipedia.net/dota2/DotaTV)、社区共识）。
- 本次实测佐证：OpenDota `/api/live` 返回字段 `delay: 120`。

**OpenDota `/api/live` 实测（降级路径的真实性）：**
- `GET https://api.opendota.com/api/live` → HTTP 200，**100 场直播比赛**，141 KB。
- 单场字段：`game_time`、`radiant_score`/`dire_score`、`radiant_lead`（经济差）、`building_state`、`spectators`、`average_mmr`、`delay: 120`、`is_watch_eligible`、**`players[10]`（含 hero_id + account_id）**。
- 示例（match 8950572444）：game_time 1894s、比分 20:36、avg_mmr 7898、9 名观众。
- 注意：该数据的**来源未被官方文档化**（LaneMind 曾称 OpenDota"不消费实时 GSI 流"，但本接口实测存在且工作正常；字段特征 `delay`/`server_steam_id`/`building_state` 指向"客户端观战采集"路径）。覆盖面 = 进入直播池的热门场次，**非任意比赛**。

### 对"实时观战辅助"的直接判定
- **秒级真实时（如比赛进行中实时镜像、实时敌方视野/行为洞察）→ 不可行**，无公开数据源。
- **准实时（约 2 分钟延迟）的赛况速览 → 可行**：比分、经济差、BP 英雄、选手/队伍识别都能从 `/api/live` 拿到，适合"直播流数据看板 / 观赛侧信息展示"，**不适合给比赛中的选手做战术辅助**（延迟即作弊风险窗口，且 GSI 本身只覆盖本地局）。

---

## 验证 3：STRATZ / OpenDota 数据时效 —— 赛后解析级，**T+分钟~小时**，**不支持秒级实时**

### 结论
- **版本追踪 / 赛后复盘（T+0 或 T+1）→ 可行**：两者都基于"赛后再放回放文件 + 解析管线"，分钟~小时级延迟，做 T+0/T+1 的聚合完全够用。
- **"实时"→ 不可行**：唯一准实时源是 OpenDota `/api/live`（120s 延迟、热门场次覆盖），不构成"实时"。

### 证据（本次实测 + 官方管线说明）
- **实测时间轴**：
  - 开打 7 分钟的比赛 → 只有骨架（duration=0、hero 数据为空）；
  - 结束约 12~15 分钟的比赛 → 有基础数据（duration、kills、hero_id），但 `version=null`（**完整回放解析未完成**）；
  - 结束约 28 小时的 TI 比赛 → 完整解析（325KB，全字段）。
- **主动请求解析**：`POST /api/request/{match_id}` → 返回 `{"job":{"jobId":470500859}}`（HTTP 200），但任务以 **priority=-2（低优先级）** 入队，**实测 3 分钟后仍未开始**。无 API key 时解析排队很慢。
- **STRATZ 解析管线**（官方 knowledge-base）：先等 Valve 放出回放文件 → 下载 → 进解析队列 → 完成后才出现在个人页；**已登录 STRATZ 的用户进高优先级队列**，游戏进行中登录会自动触发解析；Valve 维护/版本更新时会出现明显 backlog（[STRATZ-Esports/knowledge-base #24](https://github.com/stratz-esports/knowledge-base/issues/24)）。无精确"赛后多少分钟"的公开数字，量级为**分钟~小时**。
- **STRATZ 接入门槛**：GraphQL 端点 `api.stratz.com/graphql` 实测无 key 时被 Cloudflare 拦截；需 bearer token（`stratz.com/api` 可申请免费 token；第三方资料称免费层约 50 次/天，[Pipeworx STRATZ 文档](https://pipeworx.io/docs/reference/stratz/)）。**额度需以实际注册为准**。

---

## 验证 4：回放解析（.dem）技术成本 —— ✅ **可行**，且不必自建全量管线

### 结论
解析本身很快（秒级~分钟级/场），真正的成本在**下载 + 解压 + 规模化运维**。且 **OpenDota/STRATZ 已对所有公开比赛做过解析并缓存**，通常无需自建。

### 证据
- **文件大小（本次实测）**：TI 2026 那场 68 分钟比赛的 `.dem.bz2` = **263,049,761 字节（约 251 MiB，压缩后）**。社区共识：常规对局约 1 MB/分钟、50–100 MB/场（带解说音频的会更大）。
- **解析器性能（社区基准，现代硬件更快）**：
  | 解析器 | 语言 | 基准 | 资源 |
  |---|---|---|---|
  | Clarity | Java | 127MB TI 决赛回放**全量 5.12s**（旧 i5-3570k） | 流式模式 `-Xmx20m` |
  | smoke | Python/Cython | 57 分钟 TI 局 ≈33s；47 分钟路人局 ≈19s | — |
  | Haste | Rust | 38 分钟局 ≈**0.65s** | 峰值 ~18MB |
  | deadem/dota2 | JS/Node | 30 分钟局 ≈2.1s（默认） | RSS ~330MB |
  | Eaglesong | .NET | 1 小时局 ≈26.8s | — |
  | **gem-dota** | Python | 官方明言**慢于** Manta(Go)/Clarity(Java)，但输出 pandas/Parquet/JSON，面向 ML | 自带 `batch` CLI |
- **规模化判断**：瓶颈依次是 ① 从 Steam CDN 下载（单场 50–263MB）、② bz2 解压（CPU 密集）、③ 派生统计计算。解析器本体用 Go(Manta)/Java(Clarity)/Rust(Haste) 时，单核每核每小时可处理数十场。OpenDota 本身就是用 [odota/parser](https://github.com/odota/parser)（Clarity 系）做同样的事。
- **gem-dota 定位**：适合"下载回放 → 本地/离线批量出分析数据（Parquet/DataFrame）"的 ML 工作流；若要做高吞吐服务器端解析，选 Manta/Clarity/Haste，gem-dota 仅做离线衍生计算。

---

## 汇总表：免费 / 有限制 / 拿不到

| 数据 | 来源 | 成本 / 限制 | 时效 | 判定 |
|---|---|---|---|---|
| 英雄胜率 / 出场率 / 趋势 | OpenDota `/heroStats` | 免费，无 key 约 60/min、3000/day/IP | 聚合数据 | ✅ **免费可拿** |
| 赛后比赛详情（复盘） | OpenDota `/matches/{id}` | 免费；已解析比赛直接取 | T+分钟~小时 | ✅ **免费可拿**（有延迟）|
| 职业比赛列表 / 队伍 | OpenDota `/proMatches` | 免费 | 近实时 | ✅ **免费可拿** |
| 直播比赛快照（10 人英雄/比分/经济） | OpenDota `/live` | 免费 | **~120s 延迟**，仅热门场次 | ⚠️ **部分可行** |
| 主动请求解析 | OpenDota `/request/{id}` | 无 key 低优先级（实测 3min 未完成） | 不定 | ⚠️ **受限** |
| STRATZ 全量数据 | STRATZ GraphQL | 需 bearer token（免费 token 可申请，额度以实际为准） | 赛后解析管线 | ⚠️ **需 key/额度** |
| GSI 实时数据（自己打的局） | Valve GSI | 需本地跑 Dota2 客户端 | 实时 | ⚠️ **仅限自身局** |
| GSI 观战任意比赛 | Valve GSI | **无此能力** | — | ❌ **拿不到** |
| `.dem` 回放文件 | Steam CDN（`replay_url`） | 免费下载，单场 50–263MB | T+（赛后可下） | ✅ **免费可拿**（有流量成本）|
| 任意比赛的秒级实时数据 | 无公开源 | — | — | ❌ **拿不到** |

---

## 对方案的直接影响

1. **"实时观战辅助" → 降级，不砍**：
   - 原设想（比赛进行中秒级获取实时数据）**不可行**——GSI 只能覆盖本地局，无网络订阅任意比赛的通道。
   - 降级为 **"准实时赛况速览"（约 2 分钟延迟）**：基于 OpenDota `/api/live` 拉取比分、经济差、10 人英雄、选手识别，适合**观赛侧 / 直播流看板**；若产品定位是"给观赛用户的信息增强"，2 分钟延迟可接受，方案成立。
   - 若定位是"给比赛中的选手做实时战术辅助"→ **直接砍掉该功能**（延迟既是技术问题也是规则/道德问题）。

2. **赛后复盘 / 版本追踪（T+0/T+1）→ 成立**：OpenDota `/matches/{id}` + `/heroStats` 免费且字段完备，直接作为数据底座；解析延迟（分钟~小时）不影响 T+0/T+1 的聚合与报表。

3. **英雄池 / 数据平台 → 成立**：heroStats 免费、127 英雄、含 pub/pro/turbo 三套口径，MVP 零成本起步。

4. **自建回放解析 → 推迟**：MVP 阶段用 OpenDota/STRATZ 现成数据；需要自定义衍生指标（如自定义团战识别、模型特征）时，用 gem-dota（离线 Python 批次）或 Haste/Manta（服务器端）做，技术风险低、成本主要是下载带宽。

---

## 剩余不确定点（下一步验证）

1. **OpenDota `/api/live` 的来源与覆盖规则**：数据到底来自哪条采集链路？是否覆盖职业比赛？场次筛选机制？→ 深挖：拿同一场 live 数据与赛后解析数据对比一致性，并观察职业比赛的 live 覆盖。
2. **无 key 时主动解析请求的真实完成时间**：实测 3 分钟未开始（priority=-2）。→ 用带 API key 的账号对比完成耗时，决定是否把"请求解析"纳入产品流程。
3. **STRATZ 免费层真实额度与字段差异**：第三方称 50 次/天，与官方口径可能不符。→ 注册 key 实测额度、延迟、以及其相对 OpenDota 的增量字段。
4. **客户端内观战"任意玩家比赛"的具体限制**：Watch 标签的筛选/可搜性机制（能否观战指定玩家/指定 MMR 段位）。→ 用真实 Dota 2 客户端实测观战入口。
5. **GSI 观战模式下的数据完整性**：不同来源对"观战时是否含全部 10 人玩家数据"说法不一。→ 用自己客户端观战一场，抓取 GSI payload 实测 `player`/`map` 段实际内容。
6. **回放下载带宽成本**：单场 50–263MB，规模化后 CDN 下载量与费用需估算（若做自建解析）。

---

### 引用来源
- OpenDota API：`api.opendota.com`（本次全部为实际调用结果）
- GSI 机制：[/github/antonpup/Dota2GSI](https://github.com/antonpup/Dota2GSI)、[MrBean355/dota2-gsi Wiki](https://github-wiki-see.page/m/MrBean355/dota2-gsi/wiki/Library-Guide)、[ValveSoftware/Dota2-Gameplay#27260](https://github.com/ValveSoftware/Dota2-Gameplay/issues/27260)
- DotaTV 延迟：[Liquipedia DotaTV](https://liquipedia.net/dota2/DotaTV)
- STRATZ：[STRATZ knowledge-base #24](https://github.com/stratz-esports/knowledge-base/issues/24)、[Pipeworx STRATZ 文档](https://pipeworx.io/docs/reference/stratz/)
- 解析器：[odota/parser](https://github.com/odota/parser)、[dotabuff/manta](https://pkg.go.dev/github.com/dotabuff/manta)、[gem-dota 文档](https://whanyu1212.github.io/gem-dota/)、[smoke](https://github.com/cdsnz/smoke)、[deadem](https://github.com/Igor-Losev/deadem)、[Haste](https://deepwiki.com/johnpyp/haste/1.1-features-and-design-philosophy)
