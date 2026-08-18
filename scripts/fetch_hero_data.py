#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_hero_data.py —— DOTA2 国服社区平台 · 数据刷新脚本
======================================================

从 OpenDota 免费 API 拉取英雄统计（GET /api/heroStats），计算并输出
site/data/herostats.json，供静态站 report.html 渲染三类榜单。

特性
----
- 仅依赖 Python 标准库（urllib.request），无第三方依赖。
- 失败时（网络异常 / 非 200）保留上一次生成的数据，不破坏线上站点。
- 原子写入（临时文件 + os.replace），cron 重复执行安全、幂等。
- 内置 OpenDota 免费层限流考虑：单次请求 + 失败退避重试，
  全天最多约 1~2 次请求，远低于 60 次/分、3000 次/天的限额。
- 可选 --markdown 生成同款「版本周报」markdown 文本（便于发论坛/存档）。

用法
----
    python3 scripts/fetch_hero_data.py            # 仅刷新 JSON
    python3 scripts/fetch_hero_data.py --markdown # 同时生成周报 markdown

cron 示例（每天 08:03 刷新，随用户时区执行）：
    3 8 * * *  cd /path/to/dota2-platform && /usr/bin/python3 scripts/fetch_hero_data.py >> cron.log 2>&1
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# 路径与常量
# --------------------------------------------------------------------------- #

BASE_DIR = Path(__file__).resolve().parent.parent          # 仓库根目录
OUTPUT_JSON = BASE_DIR / "site" / "data" / "herostats.json"
OUTPUT_MD = BASE_DIR / "site" / "data" / "weekly_report.md"
OUTPUT_PNG = BASE_DIR / "site" / "data" / "weekly_report.png"

API_URL = "https://api.opendota.com/api/heroStats"          # OpenDota 数据源
HTTP_TIMEOUT = 25           # 单次请求超时（秒）
MAX_ATTEMPTS = 3            # 请求失败重试次数
RETRY_BACKOFF = (2, 4)      # 重试间隔（秒）

MIN_PUB_PICK = 5000         # 胜率榜最小出场样本（避免小样本噪声）
GAP_WINRATE_TOP = 25        # 认知差：路人胜率排名进入前 25
GAP_PICK_BOTTOM = 50        # 认知差：出场率排名在 50 名之后（玩的人少）
TOP_N = 10                  # 各类榜单展示条数（前端也以此为上限）

# 英雄头像 CDN（OpenDota 返回相对路径，需拼上完整域名；
# cloudflare.steamstatic.com 为 Valve 官方静态资源 CDN，已验证可访问）
IMG_BASE = "https://cdn.cloudflare.steamstatic.com"
USER_AGENT = "dota2-community-site/1.0 (github.com/dota2-platform)"

# --------------------------------------------------------------------------- #
# 英雄英文名 -> 国服中文名映射（键名与 OpenDota 返回的 localized_name 完全一致）
# --------------------------------------------------------------------------- #
CN_NAMES = {
    "Anti-Mage": "敌法师", "Axe": "斧王", "Bane": "祸乱之源",
    "Bloodseeker": "血魔", "Crystal Maiden": "水晶室女", "Drow Ranger": "卓尔游侠",
    "Earthshaker": "撼地者", "Juggernaut": "主宰", "Mirana": "米拉娜",
    "Morphling": "变体精灵", "Shadow Fiend": "影魔", "Phantom Lancer": "幻影长矛手",
    "Puck": "帕克", "Pudge": "屠夫", "Razor": "雷泽",
    "Sand King": "沙王", "Storm Spirit": "风暴之灵", "Sven": "斯温",
    "Tiny": "小小", "Vengeful Spirit": "复仇之魂", "Windranger": "风行者",
    "Zeus": "宙斯", "Kunkka": "昆卡", "Lina": "莉娜",
    "Lion": "莱恩", "Shadow Shaman": "暗影萨满", "Slardar": "斯拉达",
    "Tidehunter": "潮汐猎人", "Witch Doctor": "巫医", "Lich": "巫妖",
    "Riki": "力丸", "Enigma": "谜团", "Tinker": "修补匠",
    "Sniper": "狙击手", "Necrophos": "瘟疫法师", "Warlock": "术士",
    "Beastmaster": "兽王", "Queen of Pain": "痛苦女王", "Venomancer": "剧毒术士",
    "Faceless Void": "虚空假面", "Wraith King": "骷髅王", "Death Prophet": "死亡先知",
    "Phantom Assassin": "幻影刺客", "Pugna": "帕格纳", "Templar Assassin": "圣堂刺客",
    "Viper": "蝮蛇", "Luna": "露娜", "Dragon Knight": "龙骑士",
    "Dazzle": "戴泽", "Clockwerk": "发条技师", "Leshrac": "拉席克",
    "Nature's Prophet": "先知", "Lifestealer": "噬魂鬼", "Dark Seer": "黑暗贤者",
    "Clinkz": "克林克兹", "Omniknight": "全能骑士", "Enchantress": "魅惑魔女",
    "Huskar": "哈斯卡", "Night Stalker": "暗夜魔王", "Broodmother": "育母蜘蛛",
    "Bounty Hunter": "赏金猎人", "Weaver": "编织者", "Jakiro": "杰奇洛",
    "Batrider": "蝙蝠骑士", "Chen": "陈", "Spectre": "幽鬼",
    "Ancient Apparition": "极寒幽魂", "Doom": "末日使者", "Ursa": "熊战士",
    "Spirit Breaker": "裂魂人", "Gyrocopter": "矮人直升机", "Alchemist": "炼金术士",
    "Invoker": "祈求者", "Silencer": "沉默术士", "Outworld Devourer": "殁境神蚀者",
    "Lycan": "狼人", "Brewmaster": "酒仙", "Shadow Demon": "暗影恶魔",
    "Lone Druid": "德鲁伊", "Chaos Knight": "混沌骑士", "Meepo": "地卜师",
    "Treant Protector": "树精卫士", "Ogre Magi": "食人魔魔法师", "Undying": "不朽尸王",
    "Rubick": "拉比克", "Disruptor": "干扰者", "Nyx Assassin": "司夜刺客",
    "Naga Siren": "娜迦海妖", "Keeper of the Light": "光之守卫", "Io": "艾欧",
    "Visage": "维萨吉", "Slark": "斯拉克", "Medusa": "美杜莎",
    "Troll Warlord": "巨魔战将", "Centaur Warrunner": "半人马战行者", "Magnus": "马格纳斯",
    "Timbersaw": "伐木机", "Bristleback": "刚背兽", "Tusk": "巨牙海民",
    "Skywrath Mage": "天怒法师", "Abaddon": "亚巴顿", "Elder Titan": "上古巨神",
    "Legion Commander": "军团指挥官", "Techies": "工程师", "Ember Spirit": "灰烬之灵",
    "Earth Spirit": "大地之灵", "Underlord": "深渊领主", "Terrorblade": "恐怖利刃",
    "Phoenix": "凤凰", "Oracle": "神谕者", "Winter Wyvern": "寒冬飞龙",
    "Arc Warden": "天穹守望者", "Monkey King": "齐天大圣", "Dark Willow": "邪影芳灵",
    "Pangolier": "石鳞剑士", "Grimstroke": "天涯墨客", "Hoodwink": "森海飞霞",
    "Void Spirit": "虚无之灵", "Snapfire": "电炎绝手", "Mars": "玛尔斯",
    "Ring Master": "百戏大王", "Dawnbreaker": "破晓辰星", "Marci": "玛西",
    "Primal Beast": "兽", "Muerta": "琼英碧灵", "Kez": "凯",
    "Largo": "朗戈",
}


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #

def log(msg: str) -> None:
    """统一输出到 stderr，避免污染 stdout（stdout 留给机器可读的摘要）。"""
    print(msg, file=sys.stderr, flush=True)


def build_img_url(rel_path) -> str:
    """把 OpenDota 返回的相对图片路径拼成完整 URL，并去掉尾部的 ? 查询串。"""
    if not rel_path:
        return ""
    rel = rel_path.split("?", 1)[0]
    if rel.startswith("http"):
        return rel
    return IMG_BASE + rel


def fetch_json(url: str) -> list:
    """请求 JSON 接口，带超时与退避重试。全部失败则抛出最后一次异常。"""
    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status} {url}")
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # 网络/超时/解析错误统一视为可重试
            last_err = exc
            if attempt < MAX_ATTEMPTS:
                wait = RETRY_BACKOFF[min(attempt - 1, len(RETRY_BACKOFF) - 1)]
                log(f"[warn] 第 {attempt}/{MAX_ATTEMPTS} 次请求失败"
                    f"（{type(exc).__name__}: {exc}），{wait}s 后重试…")
                time.sleep(wait)
    raise last_err


def atomic_write(path: Path, text: str) -> None:
    """先写临时文件再 os.replace，避免写一半崩溃留下损坏的 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# 数据变换：原始 API -> 站点 JSON
# --------------------------------------------------------------------------- #

def compute_stats(raw: list) -> dict:
    """把 OpenDota heroStats 原始数组转换为站点 JSON 结构。"""
    heroes = []
    total_picks = sum(int(h.get("pub_pick") or 0) for h in raw)

    for h in raw:
        pub_pick = int(h.get("pub_pick") or 0)
        pub_win = int(h.get("pub_win") or 0)
        pro_pick = int(h.get("pro_pick") or 0)
        pro_win = int(h.get("pro_win") or 0)
        heroes.append({
            "id": h.get("id"),
            "name": CN_NAMES.get(h.get("localized_name"), h.get("localized_name")),
            "name_en": h.get("localized_name"),
            "img": build_img_url(h.get("img")),
            "roles": h.get("roles") or [],
            # 路人数据
            "pub_pick": pub_pick,
            "pub_win": pub_win,
            "pub_winrate": round(pub_win / pub_pick * 100, 2) if pub_pick else None,
            "pub_ban": int(h.get("pub_ban") or 0),
            "pick_share_pct": round(pub_pick / total_picks * 100, 3) if total_picks else 0,
            # 职业数据
            "pro_pick": pro_pick,
            "pro_win": pro_win,
            "pro_winrate": round(pro_win / pro_pick * 100, 2) if pro_pick else None,
            "pro_ban": int(h.get("pro_ban") or 0),
            # 排名在下方统一计算
            "winrate_rank": None,
            "pick_rank": None,
            "pro_rank": None,
            "is_gap": False,
        })

    # —— 路人胜率排名（样本足够的英雄，按胜率降序）——
    qualified = [h for h in heroes if h["pub_pick"] >= MIN_PUB_PICK and h["pub_winrate"] is not None]
    qualified.sort(key=lambda h: h["pub_winrate"], reverse=True)
    for rank, h in enumerate(qualified, 1):
        h["winrate_rank"] = rank

    # —— 出场率排名（全部英雄，按路人出场降序）——
    by_pick = sorted(heroes, key=lambda h: h["pub_pick"], reverse=True)
    for rank, h in enumerate(by_pick, 1):
        h["pick_rank"] = rank

    # —— 职业参考排名（仅统计有职业出场的英雄，按职业出场降序）——
    pro_only = sorted([h for h in heroes if h["pro_pick"] > 0],
                      key=lambda h: h["pro_pick"], reverse=True)
    for rank, h in enumerate(pro_only, 1):
        h["pro_rank"] = rank

    # —— 认知差标记：路人胜率高（前 25）但玩的人少（出场 50 名后）——
    for h in heroes:
        if h["winrate_rank"] and h["winrate_rank"] <= GAP_WINRATE_TOP \
                and h["pick_rank"] >= GAP_PICK_BOTTOM:
            h["is_gap"] = True

    gap_ids = [h["id"] for h in sorted(heroes, key=lambda h: h["winrate_rank"] or 999)
               if h["is_gap"]]

    return {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "data_date": datetime.now().strftime("%Y-%m-%d"),
        "source_url": API_URL,
        "version": 1,
        "min_pub_pick": MIN_PUB_PICK,
        "total_pub_picks": total_picks,
        "heroes": sorted(heroes, key=lambda h: h["pick_rank"]),   # 默认按出场率排序输出
        "gap_ids": gap_ids,
        "summary": {
            "total_heroes": len(heroes),
            "gap_count": len(gap_ids),
            "pro_sample_heroes": len(pro_only),
        },
        "highlights": build_highlights(heroes, gap_ids),
    }


def build_highlights(heroes: list, gap_ids: list) -> dict:
    """从已计算好的数据里提炼首页「本期版本要点」摘要。

    全部取自现有计算字段、不额外拉数据；任一子项缺失时对应字段输出 null，
    供前端做占位降级。version_label 为写死的当前版本号，改版时更新此处即可。
    """
    top_wr = top_pick = top_gap = None
    hot_ban = None

    # 全分段胜率最高（与胜率榜同口径：出场样本达标 + 胜率有效）
    qualified = [h for h in heroes
                 if h["pub_pick"] >= MIN_PUB_PICK and h["pub_winrate"] is not None]
    if qualified:
        top_wr = max(qualified, key=lambda h: h["pub_winrate"])

    # 出场率最高
    if heroes:
        top_pick = max(heroes, key=lambda h: h["pub_pick"])

    # 认知差最强：gap_ids 已按 winrate_rank 升序，第一个即胜率排名最高
    if gap_ids:
        by_id = {h["id"]: h for h in heroes}
        top_gap = by_id.get(gap_ids[0])

    # 路人禁选最高且进入出场前十的英雄；OpenDota 现多返回 0/None，
    # 仅在存在 >0 禁选样本时才输出，避免「禁选 0」误导
    top10_ids = {h["id"] for h in sorted(heroes, key=lambda h: h["pick_rank"])[:TOP_N]}
    ban_cands = [h for h in heroes if h["id"] in top10_ids and (h["pub_ban"] or 0) > 0]
    if ban_cands:
        hot_ban = max(ban_cands, key=lambda h: h["pub_ban"])["name"]

    return {
        "version_label": "7.41e",          # 当前版本号（改版时更新）
        "top_winrate_hero": ({
            "name": top_wr["name"],
            "winrate": top_wr["pub_winrate"],
            "pick_rank": top_wr["pick_rank"],
        } if top_wr else None),
        "top_pick_hero": ({
            "name": top_pick["name"],
            "pick": top_pick["pub_pick"],
            "winrate": top_pick["pub_winrate"],
        } if top_pick else None),
        "top_gap_hero": ({
            "name": top_gap["name"],
            "winrate": top_gap["pub_winrate"],
            "pick_rank": top_gap["pick_rank"],
        } if top_gap else None),
        "hot_ban_hero": hot_ban,
    }


# --------------------------------------------------------------------------- #
# 可选：生成「版本周报」markdown（便于发 NGA / 贴吧 / 存档）
# --------------------------------------------------------------------------- #

def render_markdown(payload: dict) -> str:
    heroes = payload["heroes"]
    def fmt(v):  # 数字千分位
        return f"{v:,}" if isinstance(v, int) else v

    lines = [
        "# 【DOTA2 国服周报】版本阵容速览",
        "",
        f"> 数据来源：OpenDota 官方 API（heroStats），抓取时间 {payload['generated_at']}",
        f"> 统计口径：全分段路人局（出场 ≥{MIN_PUB_PICK} 场 / 英雄）；职业局样本单独标注，仅供参考",
        f"> 更新日期：{payload['data_date']}",
        "",
        "---",
        "",
        "## 🏆 一、全分段路人胜率 TOP10（版本真神）",
        "",
        "> 口径：胜率 = 胜场 / 出场，且出场 ≥5000 场，避免小样本噪声。",
        "",
        "| 排名 | 英雄 | 胜率 | 出场(万) | 备注 |",
        "|---|---|---|---|---|",
    ]
    top_wr = sorted([h for h in heroes if h["winrate_rank"]], key=lambda h: h["winrate_rank"])[:TOP_N]
    for h in top_wr:
        lines.append(f"| {h['winrate_rank']} | **{h['name']} {h['name_en']}** | "
                     f"{h['pub_winrate']:.2f}% | {fmt(round(h['pub_pick']/10000, 1))} | "
                     f"{'🔶 认知差' if h['is_gap'] else '—'} |")

    lines += ["", "## 🔥 二、路人局出场率 TOP10（大家都在玩什么）", "", "> 口径：全分段出场场次。", "",
              "| 排名 | 英雄 | 出场(万) | 胜率 |", "|---|---|---|---|"]
    top_pick = sorted(heroes, key=lambda h: h["pick_rank"])[:TOP_N]
    for h in top_pick:
        wr = f"{h['pub_winrate']:.2f}%" if h["pub_winrate"] is not None else "—"
        lines.append(f"| {h['pick_rank']} | **{h['name']}** | {fmt(round(h['pub_pick']/10000, 1))} | {wr} |")

    lines += ["", "## 💎 三、认知差英雄（又强又少人玩 → 上分密码）", "",
              f"> 定义：路人胜率排名前 {GAP_WINRATE_TOP}，但出场排名在 {GAP_PICK_BOTTOM} 名之后。", ""]
    gaps = sorted([h for h in heroes if h["is_gap"]], key=lambda h: h["winrate_rank"])
    if gaps:
        for h in gaps:
            lines.append(f"- **{h['name']}（{h['name_en']}）**：路人胜率 {h['pub_winrate']:.2f}%，"
                         f"出场排名 #{h['pick_rank']}，胜率排名 #{h['winrate_rank']}")
    else:
        lines.append("- 本期暂无满足条件的认知差英雄。")

    lines += ["", "## 📊 四、职业参考（样本稀疏，谨慎参考）", "",
              "> ⚠️ 职业比赛样本随赛季波动，数据仅供方向性参考。", "",
              "| 排名 | 英雄 | 职业出场 | 职业胜率 | 职业禁用 |", "|---|---|---|---|---|"]
    top_pro = sorted([h for h in heroes if h["pro_rank"]], key=lambda h: h["pro_rank"])[:TOP_N]
    for h in top_pro:
        wr = f"{h['pro_winrate']:.2f}%" if h["pro_winrate"] is not None else "—"
        lines.append(f"| {h['pro_rank']} | **{h['name']}** | {fmt(h['pro_pick'])} | {wr} | {fmt(h['pro_ban'])} |")

    lines += ["", "---", "",
              "## ✅ 本期小结",
              "",
              "1. **新手入坑首选**：骷髅王、复仇之魂、巫妖（简单、强、容错高）。",
              "2. **想上分跟 meta 走**：胜率 TOP10 里挑你会的那个。",
              "3. **想剑走偏锋上分**：认准「认知差」英雄（又强又少人玩，吃版本红利）。",
              "4. 胜率随时间波动，本表为抓取时点快照；职业局样本在大型赛事前偏少，仅供参考。",
              "",
              "## ℹ️ 数据与声明",
              "",
              f"- **数据来源**：OpenDota API（heroStats，抓取时间 {payload['generated_at']}），全量 {payload['summary']['total_heroes']} 英雄",
              "- **免责**：本平台为**非官方社区项目**，意在帮助国服玩家入坑与提升，数据仅供参考。",
              "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 可选：把「版本周报」渲染成一张竖向长图（便于发贴吧 / NGA / B站）
# --------------------------------------------------------------------------- #
# 依赖 Pillow：pip install pillow。未安装时 render_image 返回 None，不影响其它功能。

def _find_cjk_font() -> str:
    """探测可用的中文字体路径，供 Pillow 使用。找不到则返回空串（图片会缺中文）。"""
    import glob
    candidates = [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",      # Debian/Ubuntu 文泉驿
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/System/Library/Fonts/PingFang.ttc",                # macOS
        "C:/Windows/Fonts/msyh.ttc",                          # Windows 微软雅黑
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # 兜底：任意 glob 到的 .ttc/.ttf/.otf
    for pat in ("/usr/share/fonts/**/*.tt[cf]", "/usr/share/fonts/**/*.otf"):
        hits = sorted(glob.glob(pat, recursive=True))
        if hits:
            return hits[0]
    return ""


def render_image(payload: dict) -> str:
    """把周报数据渲染成一张深色电竞风竖向长图，返回写入路径；失败返回空串。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        log("[warn] 未安装 Pillow，跳过周报长图生成（pip install pillow 可启用）")
        return ""

    W = 900                       # 画布宽
    MARGIN = 48                   # 边距
    C_BG = (10, 13, 20)           # 背景深蓝黑
    C_CARD = (22, 27, 40)         # 卡片
    C_LINE = (42, 49, 64)         # 分隔线
    C_TITLE = (255, 255, 255)     # 标题白
    C_ACCENT = (255, 90, 78)      # 主色（DOTA 红）
    C_GOLD = (255, 177, 0)        # 强调金色
    C_TEXT = (232, 234, 240)      # 正文
    C_DIM = (154, 163, 178)       # 次要文字
    LINE_H = 40                   # 行高
    TBL_H = 34                    # 表格行高

    font_path = _find_cjk_font()
    if not font_path:
        log("[warn] 未找到中文字体，跳过周报长图生成")
        return ""

    def F(size, bold=False):
        return ImageFont.truetype(font_path, size)

    f_title = F(40, bold=True)
    f_sec = F(28, bold=True)
    f_head = F(22, bold=True)
    f_body = F(22)
    f_small = F(18)

    # 收集所有绘制行，先计算总高度
    ROWS = []   # (type, text)  type: title/geo/blank/section/sub/card/gap/tblitem/summary/meta/h1/h2/table

    heroes = payload["heroes"]

    def add(*rows):
        ROWS.extend(rows)

    def top_wr():
        return sorted([h for h in heroes if h["winrate_rank"]], key=lambda h: h["winrate_rank"])[:TOP_N]
    def top_pick():
        return sorted(heroes, key=lambda h: h["pick_rank"])[:TOP_N]
    def top_pro():
        return sorted([h for h in heroes if h["pro_rank"]], key=lambda h: h["pro_rank"])[:TOP_N]
    def gaps():
        return sorted([h for h in heroes if h["is_gap"]], key=lambda h: h["winrate_rank"])

    def fmt(v):
        return f"{v:,}" if isinstance(v, int) else v

    add(("title", f"DOTA2 版本阵容周报 · {payload['data_date']}"))
    add(("geo", "数据来源 OpenDota · 非官方社区项目 · 国服入坑与版本指南"))
    add(("blank", ""))

    add(("section", "🏆 一、全分段路人胜率 TOP10"))
    add(("sub", "胜率 = 胜场/出场，样本 ≥5000 场"))
    add(("thead", ("排名", "英雄", "胜率", "出场(万)", "备注")))
    for h in top_wr():
        flag = "🔶认知差" if h["is_gap"] else ""
        add(("trow", (h["winrate_rank"], h["name"], f"{h['pub_winrate']:.2f}%",
                      f"{fmt(round(h['pub_pick']/10000,1))}", flag)))
    add(("blank", ""))

    add(("section", "🔥 二、路人局出场率 TOP10"))
    add(("theadt2", ("排名", "英雄", "出场(万)", "胜率")))
    for h in top_pick():
        wr = f"{h['pub_winrate']:.2f}%" if h["pub_winrate"] is not None else "—"
        add(("trow2", (h["pick_rank"], h["name"], f"{fmt(round(h['pub_pick']/10000,1))}", wr)))
    add(("blank", ""))

    add(("section", "💎 三、认知差英雄（又强又少人玩 → 上分密码）"))
    if gaps():
        for h in gaps():
            add(("gap", f"{h['name']}（{h['name_en']}）｜胜率 {h['pub_winrate']:.2f}% · 出场 #{h['pick_rank']} · 胜率 #{h['winrate_rank']}"))
    else:
        add(("gap", "本期暂无满足条件的认知差英雄。"))
    add(("blank", ""))

    add(("section", "📊 四、职业参考（样本稀疏，谨慎参考）"))
    add(("theadp", ("排名", "英雄", "职业出场", "职业胜率", "禁用")))
    for h in top_pro():
        wr = f"{h['pro_winrate']:.2f}%" if h["pro_winrate"] is not None else "—"
        add(("trowp", (h["pro_rank"], h["name"], fmt(h["pro_pick"]), wr, fmt(h["pro_ban"]))))
    add(("blank", ""))

    add(("section", "✅ 本期小结"))
    add(("card", "1. 新手入坑首选：骷髅王、复仇之魂、巫妖（简单强容错高）"))
    add(("card", "2. 想上分跟 meta 走：胜率 TOP10 里挑你会的那个。"))
    add(("card", "3. 想剑走偏锋上分：认准「认知差」英雄（吃版本红利）。"))
    add(("card", "4. 数据为抓取时点快照，仅供参考；职业样本在赛事淡季偏少。"))
    add(("blank", ""))

    add(("section", "ℹ️ 数据与声明"))
    add(("card2", f"数据来源：OpenDota API（heroStats，{payload['generated_at']}），全量 {payload['summary']['total_heroes']} 英雄"))
    add(("card2", "本站为非官方社区项目，数据仅供参考，与 Valve / 完美世界无关。"))
    add(("blank", ""))
    add(("card5", "🏠 每周更新 · iceamber.github.io/dota2-platform ｜ 关注不迷路"))

    # ---- 计算总高度 ----
    def row_h(r):
        t = r[0]
        if t == "title": return 58
        if t == "geo": return 30
        if t == "section": return 46
        if t == "sub": return 26
        if t == "blank": return 14
        if t in ("thead", "theadt2", "theadp", "trow", "trow2", "trowp"): return TBL_H
        if t == "gap": return 44
        if t in ("card", "card2", "card5"): return 52
        return 40
    H = MARGIN * 2 + sum(row_h(r) for r in ROWS)

    img = Image.new("RGB", (W, H), C_BG)
    d = ImageDraw.Draw(img)

    inner_left = MARGIN
    table_right = W - MARGIN
    text_w = table_right - inner_left

    def wrap(txt, font, max_w):
        """按像素宽度换行（Pillow 不支持自动换行，手动测量）。"""
        lines = []
        for para in txt.split("\n"):
            cur = ""
            for ch in para:
                if d.textlength(cur + ch, font=font) <= max_w:
                    cur += ch
                else:
                    lines.append(cur); cur = ch
            if cur:
                lines.append(cur)
        return lines

    y = MARGIN

    def draw_text(txt, font, fill, x, y, max_w=None):
        for ln in wrap(txt, font, max_w or (text_w - (x - inner_left))):
            d.text((x, y), ln, font=font, fill=fill)
            y += font.size + 8
        return y

    # 表格列宽（按列数分配）
    col_counts = {"theadt2": 4, "thead": 5, "theadp": 5}

    def draw_table(rows, ncols, widths, row_y, header_font, body_font):
        row_hh = TBL_H
        # 表头背景
        d.rectangle([inner_left, row_y, table_right, row_y + row_hh], fill=(40, 48, 66))
        y2 = row_y + (row_hh - header_font.size) / 2
        x = inner_left
        for idx, col_head in enumerate(rows[0]):
            cv = str(col_head)
            d.text((x, y2 + 4), cv, font=header_font, fill=C_GOLD)
            x += widths[idx]
        y2 = row_y + row_hh
        for data_row in rows[1:]:
            d.rectangle([inner_left, y2, table_right, y2 + row_hh], fill=C_CARD)
            yy = y2 + (row_hh - body_font.size) / 2
            xx = inner_left
            for idx, cell in enumerate(data_row):
                cv = str(cell)
                fill = C_ACCENT if idx == 0 else (C_TEXT if idx <= 2 else C_DIM)
                d.text((xx, yy + 4), cv, font=body_font, fill=fill)
                xx += widths[idx]
            y2 += row_hh
        return y2

    # 绘制主体
    # 先做两遍：把表格分组成区块，逐行画。
    tbl = []      # (ncols, rows) 连续的表格行集合
    i = 0
    # 简单起见：遇到 thead 开头，收集后续 trow 直到非表格行
    proc = []
    j = 0
    while j < len(ROWS):
        t = ROWS[j][0]
        if t in ("thead", "theadt2", "theadp"):
            ncols = col_counts[t]
            rows = [ROWS[j][1]]
            k = j + 1
            while k < len(ROWS) and ROWS[k][0] in ("trow", "trow2", "trowp"):
                rows.append(ROWS[k][1])
                k += 1
            proc.append(("table", ncols, rows))
            j = k
        else:
            proc.append(("row", ROWS[j]))
            j += 1

    for item in proc:
        if item[0] == "row":
            r = item[1]
            t = r[0]
            if t == "title":
                y = draw_text(r[1], f_title, C_TITLE, inner_left, y)
            elif t == "geo":
                d.line([inner_left, y + 6, table_right, y + 6], fill=C_GOLD, width=3)
                y = draw_text(r[1], f_small, C_DIM, inner_left, y + 14)
            elif t == "section":
                d.rectangle([inner_left, y, inner_left + 8, y + 30], fill=C_ACCENT)
                y = draw_text(r[1], f_sec, C_TITLE, inner_left + 20, y)
            elif t == "sub":
                y = draw_text(r[1], f_small, C_DIM, inner_left + 4, y)
            elif t == "gap":
                txt_h = f_body.size + 8 + 14
                d.rounded_rectangle([inner_left, y, table_right, y + txt_h + 10], radius=8, fill=(46, 34, 18), outline=(120, 84, 20))
                y = draw_text(r[1], f_body, C_GOLD, inner_left + 14, y + 8, max_w=text_w - 28)
            elif t in ("card", "card2"):
                txt_h = f_body.size + 8 + 14
                d.rounded_rectangle([inner_left, y, table_right, y + txt_h + 10], radius=8, fill=C_CARD)
                y = draw_text(r[1], f_body, C_TEXT, inner_left + 14, y + 8, max_w=text_w - 28)
            elif t == "card5":
                txt_h = f_body.size + 8 + 14
                d.rounded_rectangle([inner_left, y, table_right, y + txt_h + 10], radius=8, fill=(34, 20, 12), outline=C_ACCENT)
                y = draw_text(r[1], f_body, C_GOLD, inner_left + 14, y + 8, max_w=text_w - 28)
            # blank 不做绘制，仅占位(y 自动推进)
        else:
            ncols, rows = item[1], item[2]
            # 根据列数给列宽
            if ncols == 4:
                widths = [90, 240, 160, 140]
            else:
                widths = [90, 240, 150, 150, 140]
            y = draw_table(rows, ncols, widths, y, f_head, f_body)
            y += 6

    OUTPUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT_PNG, "PNG")
    return str(OUTPUT_PNG)


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(
        description="刷新 DOTA2 英雄数据并输出 site/data/herostats.json",
        epilog="示例：python3 scripts/fetch_hero_data.py --markdown",
    )
    parser.add_argument("--markdown", action="store_true",
                        help="同时生成 site/data/weekly_report.md 周报文本")
    parser.add_argument("--image", action="store_true",
                        help="同时生成 site/data/weekly_report.png 周报长图（需 Pillow）")
    parser.add_argument("--api-url", default=API_URL,
                        help=f"覆盖数据源地址（默认 {API_URL}）")
    args = parser.parse_args()

    log(f"[info] 开始拉取数据：{args.api_url}")
    try:
        raw = fetch_json(args.api_url)
    except Exception as exc:
        # 关键兜底：失败时绝不覆盖已有数据
        if OUTPUT_JSON.exists():
            mtime = datetime.fromtimestamp(OUTPUT_JSON.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            log("[error] 数据获取失败，已保留上次生成的数据")
            log(f"        上次数据时间：{mtime} → {OUTPUT_JSON.relative_to(BASE_DIR)}")
        else:
            log("[error] 数据获取失败，且当前没有历史数据可保留")
        log(f"        失败原因：{type(exc).__name__}: {exc}")
        return 1

    payload = compute_stats(raw)
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    atomic_write(OUTPUT_JSON, text)
    log(f"[ok] 已写入 {OUTPUT_JSON.relative_to(BASE_DIR)}"
        f"（{len(raw)} 英雄，{len(payload['heroes'])} 条有效记录）")

    if args.markdown:
        atomic_write(OUTPUT_MD, render_markdown(payload))
        log(f"[ok] 已写入 {OUTPUT_MD.relative_to(BASE_DIR)}")

    if args.image or args.markdown:
        png = render_image(payload)
        if png:
            log(f"[ok] 已写入周报长图 {OUTPUT_PNG.relative_to(BASE_DIR)}")

    # stdout 输出机器可读摘要
    print(json.dumps({
        "ok": True,
        "file": str(OUTPUT_JSON.relative_to(BASE_DIR)),
        "heroes": payload["summary"]["total_heroes"],
        "gap_heroes": payload["summary"]["gap_count"],
        "generated_at": payload["generated_at"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
