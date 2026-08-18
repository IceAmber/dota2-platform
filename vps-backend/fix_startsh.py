#!/usr/bin/env python3
# 修复 start.sh：用 .env 里的真实值覆盖假占位符(长度<=4)的 export 值
import re, os

ENV = "/opt/ai-launcher-backend/.env"
SH  = "/opt/ai-launcher-backend/start.sh"

def load_env(path):
    d = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        d[k.strip()] = v.strip()
    return d

env = load_env(ENV)
lines = open(SH, encoding="utf-8").read().splitlines()
changed = []
out = []
for line in lines:
    m = re.match(r'^export\s+([A-Z_]+)=(.+)$', line.strip())
    if m:
        k, v = m.group(1), m.group(2)
        # 只替换明显是占位符的假值（长度<=4，如 ***）
        if len(v) <= 4 and k in env:
            nv = env[k]
            out.append(f'export {k}={nv}')
            changed.append(f'{k}: "{v}" -> "{nv[:6]}...(len={len(nv)})"')
            continue
    out.append(line)

if changed:
    with open(SH, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("已修复以下变量:")
    for c in changed:
        print("  ", c)
else:
    print("无需修复（没有发现假占位符，或 .env 缺对应键）")

# 校验：重跑修复看是否幂等
print("\n=== 修复后 start.sh 键值长度校验 ===")
for line in out:
    m = re.match(r'^export\s+([A-Z_]+)=(.+)$', line.strip())
    if m and m.group(1) in ("CLIENT_API_KEY","DEEPSEEK_API_KEY","DEFAULT_LLM_PROVIDER","DEEPSEEK_MODEL","PORT"):
        print(f"  {m.group(1)}: len={len(m.group(2))} prefix={m.group(2)[:4]}")
