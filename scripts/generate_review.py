#!/usr/bin/env python3
"""赛后复盘生成器（方案 B：后端生成 → 存 markdown → 前端静态展示）

用法：
  python3 scripts/generate_review.py
    # 交互式：提示输入比赛数据(JSON 或粘贴)
  python3 scripts/generate_review.py --data '{"radiant_win":true,...,"players":[...]}'
    # 直接给比赛数据 JSON
  python3 scripts/generate_review.py --data file.json
    # 从文件读比赛数据
  python3 scripts/generate_review.py --data '...' --title "XG vs LGD 胜者组决赛"
    # 指定复盘标题（slug/页面标题）
  python3 scripts/generate_review.py --title "xxx" --prompt "重点分析中单"
    # 无数据，纯战术/版本分析模式（仍给出标题）

产出：
  - site/data/reviews/{timestamp}-{slug}.md   复盘 markdown（可编辑）
  - site/data/reviews/index.json              复盘列表（前端列表页用）
流程：
  1. 调 VPS 后端 /api/review 生成 markdown
  2. 写入 site/data/reviews/
  3. 提示：git add + commit + push 触发部署
"""
import argparse, json, os, sys, time, re, pathlib, urllib.request, urllib.error

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
REVIEW_DIR = BASE_DIR / "site" / "data" / "reviews"

# 后端地址（VPS）
REVIEW_API = os.environ.get(
    "REVIEW_API",
    "https://65.49.216.139:3000/api/review",  # 带鉴权入口，需 CLIENT_API_KEY
)
# CLIENT_API_KEY 从环境变量读（不入库）
CLIENT_API_KEY = os.environ.get("CLIENT_API_KEY", "")

def read_cli_key():
    """从本地 .env.review 或环境变量取 key。"""
    if CLIENT_API_KEY:
        return CLIENT_API_KEY
    envf = BASE_DIR / ".env.review"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("CLIENT_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""

def call_review(match_data, custom_prompt):
    key = read_cli_key()
    if not key:
        print("[error] 缺少 CLIENT_API_KEY。请在环境变量或 .env.review 中提供。")
        sys.exit(1)
    payload = {"matchData": match_data, "customPrompt": custom_prompt}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(REVIEW_API, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-API-Key", key)
    # 信任自签名证书（VPS 自签名）
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print("[error] 后端 HTTP", e.code, e.read().decode("utf-8", "ignore")[:300])
        sys.exit(1)
    except Exception as e:
        print("[error] 调用后端失败:", e)
        sys.exit(1)

def slugify(s):
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", s).strip("-")
    return s or "review"

def load_match_data(arg):
    if not arg:
        return None
    # 文件？
    if os.path.isfile(arg):
        with open(arg, encoding="utf-8") as f:
            return json.load(f)
    # JSON 字符串
    try:
        return json.loads(arg)
    except json.JSONDecodeError:
        print("[error] --data 不是合法 JSON 或文件路径")
        sys.exit(1)

def main():
    ap = argparse.ArgumentParser(description="赛后复盘生成器（方案B）")
    ap.add_argument("--data", help="比赛数据：JSON 字符串或文件路径（可省略走分析模式）")
    ap.add_argument("--title", default="", help="复盘标题（用于文件名/页面）")
    ap.add_argument("--prompt", default="", help="附加提示词（如：重点分析中单）")
    ap.add_argument("--publish", action="store_true", help="生成后自动 git commit+push")
    args = ap.parse_args()

    match_data = load_match_data(args.data)
    title = args.title.strip() or (f"复盘 {time.strftime('%m-%d')}")
    slug = slugify(title)

    print(f"[info] 标题: {title}")
    print(f"[info] 调用后端生成复盘（数据: {'有' if match_data else '无(分析模式)'}）...")
    result = call_review(match_data, args.prompt)
    review_md = result.get("review", "")
    if not review_md:
        print("[error] 后端返回空复盘")
        sys.exit(1)

    # 组装 markdown（加前置 YAML 元信息 + 分享需要的字段）
    ts = time.strftime("%Y%m%d-%H%M%S")
    fname = f"{ts}-{slug}.md"
    md = (
        f"---\n"
        f"title: {title}\n"
        f"date: {ts}\n"
        f"provider: {result.get('provider','')}\n"
        f"model: {result.get('model','')}\n"
        f"source: 赛后复盘(LLM生成，数据来自提供的比赛数据)\n"
        f"---\n\n"
        f"{review_md}\n"
    )
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out = REVIEW_DIR / fname
    out.write_text(md, encoding="utf-8")
    print(f"[ok] 已写入 {out.relative_to(BASE_DIR)}")
    print(f"     provider={result.get('provider')} model={result.get('model')}")

    # 更新 index.json（前端列表）
    index_path = REVIEW_DIR / "index.json"
    items = []
    if index_path.exists():
        try:
            items = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            items = []
    items = [i for i in items if not isinstance(i, dict) or i.get("file") != fname]
    items.append({
        "file": fname,
        "title": title,
        "date": ts,
        "provider": result.get("provider", ""),
        "model": result.get("model", ""),
    })
    items.sort(key=lambda x: x.get("date", ""), reverse=True)
    index_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] 更新列表 {index_path.relative_to(BASE_DIR)} → {len(items)} 条")

    if args.publish:
        os.system(f'cd {BASE_DIR} && git add site/data/reviews/ && git commit -m "feat: 新增赛后复盘「{title}」" && git push origin main')
        print("[ok] 已提交并推送，等待部署")
    else:
        print("\n[提示] 未自动发布。确认内容后执行：")
        print(f"  cd {BASE_DIR} && git add site/data/reviews/ && git commit -m 'feat: 新增赛后复盘「{title}」' && git push origin main")
        print("  或加 --publish 参数自动提交推送。")

if __name__ == "__main__":
    main()
