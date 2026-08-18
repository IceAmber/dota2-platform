#!/usr/bin/env python3
"""TI（国际邀请赛）复盘批量生成器（方案B：后端生成 → 存 markdown → 静态展示）

特性：
  1. 全量拉取今年 TI 15 的真实比赛列表（OpenDota proMatches）
  2. 数据预处理：把 OpenDota 原始 dict 压缩成「LLM 友好」的精简摘要，不丢原始数据
  3. 缓存：某场比赛若已有复盘 md 则直接复用（不重复调 LLM，省 token）
  4. 按需生成：默认只生成含中国队的场次，支持按队伍名筛选（不做全量批量生成，省 token）
  5. 队伍信息：拉取双方 team tag + logo_url（OpenDota /api/teams/{id}，带本地缓存），写入 ti_index.json

用法：
  python3 scripts/ti_review.py --list              # 列出所有 TI 比赛+复盘状态（含队伍 tag）
  python3 scripts/ti_review.py --match 8946690366  # 只为某场生成/复用复盘
  python3 scripts/ti_review.py --china             # 默认：只生成含中国队的比赛
  python3 scripts/ti_review.py --team lgd          # 只生成指定队伍参与的场次（可多次/逗号分隔）
  python3 scripts/ti_review.py --publish           # 生成后自动 git commit+push

产出：
  - site/data/reviews/{match_id}-{slug}.md         每场复盘（有缓存则跳过）
  - site/data/reviews/ti_index.json                全 TI 赛程 + 复盘状态（前端用）
"""
import argparse, json, os, sys, time, re, pathlib, urllib.request, urllib.error, ssl

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
REVIEW_DIR = BASE_DIR / "site" / "data" / "reviews"

REVIEW_API = os.environ.get(
    "REVIEW_API", "https://65.49.216.139:3000/api/review",  # 带鉴权入口
)
TI_LEAGUE = "The International 2026"   # OpenDota league_name
CHINA_TEAMS = ["Xtreme Gaming", "Vici Gaming", "Team Resilience",
               "LGD Gaming", "BoomBoys"]  # 中国/华语队伍（含东南亚OG不计，仅中国）

_CTX = ssl.create_default_context(); _CTX.check_hostname = False; _CTX.verify_mode = ssl.CERT_NONE


def http_json(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "dota2-community/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def list_ti_matches(limit_pages=6):
    """拉 proMatches 多页，过滤出今年 TI 的真实比赛（去重）。"""
    seen = {}
    for page in range(limit_pages):
        try:
            url = f"https://api.opendota.com/api/proMatches?limit=100&offset={page*100}"
            data = http_json(url, timeout=50)
            if not data:
                break
            for m in data:
                if (m.get("league_name") or "").strip() == TI_LEAGUE:
                    seen[m["match_id"]] = m
            time.sleep(0.4)  # 限速
        except Exception as e:
            print(f"[warn] 第 {page} 页失败: {e}")
    return list(seen.values())


def is_china_match(m):
    r = (m.get("radiant_name") or "").strip()
    d = (m.get("dire_name") or "").strip()
    return r in CHINA_TEAMS or d in CHINA_TEAMS


# ---------- 队伍 tag / logo（team_id → {tag, logo_url}），内存+本地缓存 ----------
TEAM_CACHE_FILE = REVIEW_DIR / "team_cache.json"


def load_team_cache():
    if TEAM_CACHE_FILE.exists():
        try:
            return json.loads(TEAM_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_team_cache(cache):
    try:
        TEAM_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[warn] 队伍缓存写入失败: {e}")


def fetch_team_info(team_id, fallback_name, cache):
    """按 team_id 拉 OpenDota /api/teams/{id}，取 tag + logo_url。
    同队不重复拉（内存+本地缓存）。拉不到时 tag 用队名兜底、logo_url 留空。"""
    tid = str(team_id) if team_id is not None else ""
    if tid in ("", "None", "0"):
        return {"tag": fallback_name, "logo_url": ""}
    if tid in cache:
        return cache[tid]
    try:
        t = http_json(f"https://api.opendota.com/api/teams/{tid}", timeout=30)
        if not isinstance(t, dict):
            raise ValueError("非预期响应")
        info = {
            "tag": (t.get("tag") or "").strip() or (fallback_name or "").strip() or "?",
            "logo_url": t.get("logo_url") or "",
        }
    except Exception as e:
        print(f"[warn] 队伍 {tid} 信息拉取失败，用队名兜底: {e}")
        info = {"tag": (fallback_name or "").strip() or "?", "logo_url": ""}
    cache[tid] = info
    time.sleep(0.3)  # 轻量限速，避免 OpenDota 限流
    return info


def match_team_tags(m, cache):
    """取一场比赛双方 tag（拉不到则回退队伍全名）。"""
    rname = (m.get("radiant_name") or "?").strip()
    dname = (m.get("dire_name") or "?").strip()
    rt = fetch_team_info(m.get("radiant_team_id"), rname, cache).get("tag") or rname
    dt = fetch_team_info(m.get("dire_team_id"), dname, cache).get("tag") or dname
    return rt, dt


def parse_team_args(values):
    """把 --team 的值展开成队名关键词列表（支持多次出现 + 逗号分隔）。"""
    teams = []
    for v in values:
        for part in v.split(","):
            part = part.strip()
            if part:
                teams.append(part)
    return teams


def match_team_kw(team_kws, m):
    """判断一场比赛是否有任一队伍命中关键词（不区分大小写、部分匹配）。"""
    r = (m.get("radiant_name") or "").lower()
    d = (m.get("dire_name") or "").lower()
    return any(kw.lower() in r or kw.lower() in d for kw in team_kws)


def get_hero_cn_map():
    hp = BASE_DIR / "site" / "data" / "herostats.json"
    try:
        if hp.exists():
            local = json.loads(hp.read_text(encoding="utf-8"))
            return {h.get("id"): h.get("name") for h in (local.get("heroes") or []) if h.get("id")}
    except Exception:
        pass
    try:
        return {h.get("id"): h.get("localized_name") for h in http_json("https://api.opendota.com/api/heroStats", 25)}
    except Exception as e:
        print(f"[warn] 英雄名映射不可用: {e}")
        return {}


def summarize_match(match_id, hero_cn, team_cache):
    """数据预处理：拉 OpenDota 原始数据，压缩成 LLM 友好的精简摘要。
    只保留对复盘有用的维度，不丢原始结构。"""
    raw = http_json(f"https://api.opendota.com/api/matches/{match_id}", timeout=90)
    radiant = (raw.get("radiant_name") or raw.get("radiant_team") or "Radiant").strip()
    dire = (raw.get("dire_name") or raw.get("dire_team") or "Dire").strip()
    # 队伍 tag + logo_url（OpenDota /api/teams/{id}，带缓存；拉不到则队名兜底、logo 留空）
    rinfo = fetch_team_info(raw.get("radiant_team_id"), radiant, team_cache)
    dinfo = fetch_team_info(raw.get("dire_team_id"), dire, team_cache)
    radiant_win = bool(raw.get("radiant_win"))
    duration = raw.get("duration")
    # 真实比赛开始时间（unix -> 本地/UTC 字符串，用北京时区显示）
    start_ts = raw.get("start_time")
    match_time_text = ""
    if start_ts:
        try:
            import datetime
            dt = datetime.datetime.utcfromtimestamp(start_ts) + datetime.timedelta(hours=8)  # UTC+8 北京
            match_time_text = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            match_time_text = ""

    # 选手精简表
    players = []
    for p in raw.get("players", []):
        slot = p.get("player_slot")
        team = "radiant" if slot < 128 else "dire"
        players.append({
            "team": team,
            "hero": hero_cn.get(p.get("hero_id"), str(p.get("hero_id"))),
            "hero_id": p.get("hero_id"),
            "kills": p.get("kills"), "deaths": p.get("deaths"), "assists": p.get("assists"),
            "gold_per_min": p.get("gold_per_min"), "xp_per_min": p.get("xp_per_min"),
            "hero_damage": p.get("hero_damage"), "hero_healing": p.get("hero_healing"),
            "last_hits": p.get("last_hits"), "level": p.get("level"),
            "lane": p.get("lane"), "lane_role": p.get("lane_role"),
        })
    # 队伍级汇总
    def team_stats(tside):
        ps = [p for p in players if p["team"] == tside]
        return {
            "total_kills": sum(p["kills"] or 0 for p in ps),
            "total_deaths": sum(p["deaths"] or 0 for p in ps),
            "avg_gpm": round(sum(p["gold_per_min"] or 0 for p in ps) / max(1, len(ps)), 1),
            "total_damage": sum(p["hero_damage"] or 0 for p in ps),
            "player_count": len(ps),
        }
    return {
        "match_id": match_id,
        "league": (raw.get("league", {}) or {}).get("name", ""),
        "radiant_team": radiant, "dire_team": dire,
        "radiant_tag": rinfo["tag"], "radiant_logo": rinfo["logo_url"],
        "dire_tag": dinfo["tag"], "dire_logo": dinfo["logo_url"],
        "radiant_win": radiant_win,
        "winner": radiant if radiant_win else dire,
        "loser": dire if radiant_win else radiant,
        "duration_seconds": duration,
        "duration_text": f"{int(duration//60)}分{int(duration%60)}秒" if duration else None,
        "match_time": match_time_text,
        "radiant_summary": team_stats("radiant"),
        "dire_summary": team_stats("dire"),
        "players": players,
    }


def llm_prompt_data(s):
    """把完整摘要压缩成精简短文本，喂给 LLM（输入越短越不易空返回）。"""
    lines = []
    lines.append(f"赛事: {s.get('league','')}  时长: {s.get('duration_text') or '未知'}")
    lines.append(f"对阵: {s['radiant_team']}（天辉） vs {s['dire_team']}（夜魇）")
    lines.append(f"结果: {s['winner']} 获胜")
    rs = s['radiant_summary']; ds = s['dire_summary']
    lines.append(f"天辉 {s['radiant_team']}: 击杀{rs['total_kills']} 死亡{rs['total_deaths']} 平均GPM{rs['avg_gpm']} 总伤害{rs['total_damage']}")
    lines.append(f"夜魇 {s['dire_team']}: 击杀{ds['total_kills']} 死亡{ds['total_deaths']} 平均GPM{ds['avg_gpm']} 总伤害{ds['total_damage']}")
    lines.append("选手数据（英雄: 击杀/死亡/助攻, GPM, 伤害, 治疗）:")
    for p in s.get("players", []):
        lines.append(f"  {p['team']}: {p['hero']} {p['kills']}/{p['deaths']}/{p['assists']} GPM{p['gold_per_min']} 伤害{p['hero_damage']} 治疗{p['hero_healing']}")
    return "\n".join(lines)


def read_cli_key():
    k = os.environ.get("CLIENT_API_KEY", "")
    if k:
        return k
    envf = BASE_DIR / ".env.review"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("CLIENT_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def call_llm(summary, title):
    """调后端 /api/review 生成复盘（已预处理成 summary）。空结果自动重试。"""
    key = read_cli_key()
    if not key:
        print("[error] 缺少 CLIENT_API_KEY")
        sys.exit(1)
    payload = {"matchData": summary, "customPrompt": f"这是 {title} 的复盘。请用中文输出，标题可含对阵双方。"}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(REVIEW_API, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-API-Key", key)
    last = ""
    for attempt in range(1, 9):
        try:
            with urllib.request.urlopen(req, timeout=180, context=_CTX) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            review = (result.get("review") or "").strip()
            if review:
                return review
            last = f"空结果(第{attempt}次)"
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8','ignore')[:150]}"
        except Exception as e:
            last = f"{e}"
        wait = 4 * attempt
        print(f"[warn] LLM 失败({last})，{wait}s 后重试({attempt}/8)...")
        time.sleep(wait)
    print(f"[error] LLM 多次重试失败: {last}")
    sys.exit(1)


def slugify(s):
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", s).strip("-")
    return s or "match"


def match_title(m):
    return f"{m.get('radiant_name','?')} vs {m.get('dire_name','?')}"


def load_ti_index():
    p = REVIEW_DIR / "ti_index.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_ti_index(idx):
    (REVIEW_DIR / "ti_index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_review(m, hero_cn, idx, team_cache, force=False, publish=False):
    """为单场比赛生成/复用复盘。返回 (操作, 文件)。"""
    mid = str(m["match_id"])
    if not force and mid in idx and idx[mid].get("done"):
        print(f"  [cache] {match_title(m)} 已有复盘，跳过")
        return "cache", idx[mid].get("file")
    print(f"  [gen]   {match_title(m)} ...")
    summary = summarize_match(m["match_id"], hero_cn, team_cache)
    title = f"TI15 · {summary['radiant_team']} vs {summary['dire_team']} 复盘"
    # 数据先预处理成精简文本再喂 LLM（输入越短越不易空返回）
    review_md = call_llm(llm_prompt_data(summary), title)
    # 用真实比赛时间（如有）
    ts = time.strftime("%Y%m%d-%H%M%S")
    fname = f"{mid}-{slugify(title)}.md"
    # 主赛事/小组赛粗略判断（主赛事 match_id 更大）
    try:
        bo_phase = "TI15 主赛事" if 8948500000 <= int(mid) <= 8950000000 else "TI15 小组赛"
    except Exception:
        bo_phase = "TI15 小组赛"
    md = (
        "---\n"
        f"title: {title}\n"
        f"date: {ts}\n"
        f"match_id: {mid}\n"
        f"match_time: {summary.get('match_time','')}\n"
        f"duration: {summary.get('duration_text','')}\n"
        f"bo: {bo_phase} · {summary['winner']} 胜\n"
        f"source: 赛后复盘·AI 依据 OpenDota 比赛数据生成\n"
        "---\n\n"
        f"{review_md}\n"
    )
    (REVIEW_DIR / fname).write_text(md, encoding="utf-8")
    idx[mid] = {"file": fname, "title": title, "date": ts,
                "radiant": summary["radiant_team"], "dire": summary["dire_team"],
                "radiant_tag": summary.get("radiant_tag") or summary["radiant_team"],
                "radiant_logo": summary.get("radiant_logo") or "",
                "dire_tag": summary.get("dire_tag") or summary["dire_team"],
                "dire_logo": summary.get("dire_logo") or "",
                "winner": summary["winner"], "match_time": summary.get("match_time", ""),
                "duration": summary.get("duration_text", ""),
                "done": True}
    save_ti_index(idx)
    save_team_cache(team_cache)
    print(f"  [ok]   已生成 {fname}")
    return "gen", fname


def main():
    ap = argparse.ArgumentParser(description="TI 赛事复盘批量生成器")
    ap.add_argument("--list", action="store_true", help="只列出 TI 比赛+复盘状态，不生成")
    ap.add_argument("--match", help="只为指定 match_id 生成/复用")
    ap.add_argument("--china", action="store_true", help="只生成含中国队的比赛（默认行为）")
    ap.add_argument("--team", action="append", default=[], metavar="队名",
                    help="只生成指定队伍参与的场次（可多次/逗号分隔，不区分大小写、部分匹配，如 --team lgd）")
    ap.add_argument("--force", action="store_true", help="强制重新生成（忽略缓存）")
    ap.add_argument("--publish", action="store_true", help="生成后自动 git commit+push")
    args = ap.parse_args()

    print(f"[info] 拉取 {TI_LEAGUE} 比赛列表...")
    matches = list_ti_matches()
    if not matches:
        print("[error] 未拉到 TI 比赛（OpenDota 可能限流）")
        sys.exit(1)
    print(f"[info] 共 {len(matches)} 场真实 TI 比赛")
    china = [m for m in matches if is_china_match(m)]
    print(f"       其中含中国队 {len(china)} 场")

    idx = load_ti_index()
    team_cache = load_team_cache()
    # 强制刷新赛程里的队伍字段（proMatches 比缓存新）
    for m in matches:
        mid = str(m["match_id"])
        if mid not in idx:
            idx[mid] = {"radiant": m.get("radiant_name",""), "dire": m.get("dire_name",""),
                        "winner": "", "duration_text": "", "done": False}

    if args.list:
        print(f"\n{'match_id':<12}{'复盘':<6} 对阵（队伍 tag）")
        for m in sorted(matches, key=lambda x: x["match_id"], reverse=True):
            done = "✓" if idx.get(str(m["match_id"]), {}).get("done") else "·"
            rt, dt = match_team_tags(m, team_cache)
            print(f"  {m['match_id']:<12}{done:<5}{rt:<20} vs {dt}")
        save_team_cache(team_cache)
        return

    # 确定要生成的场次（优先级：--match > --team > 默认 --china；不做全量批量生成）
    team_kws = parse_team_args(args.team)
    if args.match:
        targets = [m for m in matches if str(m["match_id"]) == args.match]
        if not targets:
            print(f"[error] 未找到 match {args.match}")
            sys.exit(1)
    elif team_kws:
        targets = [m for m in matches if match_team_kw(team_kws, m)]
        if not targets:
            print(f"[error] 未找到含 {'/'.join(team_kws)} 的场次")
            sys.exit(1)
        print(f"       其中含指定队伍 {len(targets)} 场")
    else:  # 默认 china（省 token，不做全量生成）
        targets = china

    hero_cn = get_hero_cn_map()
    stats = {"gen": 0, "cache": 0}
    for m in sorted(targets, key=lambda x: x["match_id"], reverse=True):
        try:
            op, _ = ensure_review(m, hero_cn, idx, team_cache, force=args.force, publish=args.publish)
            stats[op] += 1
        except Exception as e:
            print(f"  [err]  {match_title(m)} 失败: {e}")
    save_ti_index(idx)
    save_team_cache(team_cache)
    print(f"\n完成：新生成 {stats['gen']} 篇，复用缓存 {stats['cache']} 篇")

    if args.publish:
        os.system(f'cd {BASE_DIR} && git add site/data/reviews/ && git commit -m "feat: TI15 复盘批量更新" && git push origin main')
        print("[ok] 已提交并推送")


if __name__ == "__main__":
    main()
