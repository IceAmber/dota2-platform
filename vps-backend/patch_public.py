#!/usr/bin/env python3
# 幂等插入 /api/review_public 公开入口（无 key 鉴权，仅 IP 限流 + 输入约束）
import re, sys

PATH = "/opt/ai-launcher-backend/server.js"
with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

ROUTE = r'''
// —— 公开赛后复盘入口（无鉴权，但严格 IP 限流 + 输入约束）——
// 仅用于公开展示/复盘生成，不走 CLIENT_API_KEY；靠限流与体积控制防滥用。
const reviewPublicLimit = new Map();
function reviewPublicRateLimit(ip) {
  const now = Date.now();
  const arr = (reviewPublicLimit.get(ip) || []).filter(t => now - t < 60000);
  // 每分钟 3 次，够日常复盘，防刷爆 DeepSeek 配额
  if (arr.length >= 3) return false;
  arr.push(now);
  reviewPublicLimit.set(ip, arr);
  return true;
}
app.post('/api/review_public', async (req, res) => {
  try {
    if (!reviewPublicRateLimit(req.ip)) {
      return res.status(429).json({ error: 'Too many requests, retry later' });
    }
    // 输入约束：忽略无关字段，防超大 body
    const body = (req.body && typeof req.body === 'object') ? req.body : {};
    const matchData = body.matchData || null;
    const customPrompt = typeof body.customPrompt === 'string' ? body.customPrompt.slice(0, 2000) : '';
    if (!matchData && !customPrompt) {
      return res.status(400).json({ error: 'matchData or customPrompt required' });
    }
    const ctx = { fetch, LLM_URL, LLM_MODEL, LLM_API_KEY, USE_DEEPSEEK };
    const result = await review.runReview(ctx, { matchData, customPrompt });
    const now = new Date().toISOString();
    console.log('[' + now + '] review_public OK from ' + req.ip + ' model=' + result.model + ' len=' + result.review.length);
    res.json(result);
  } catch (error) {
    const status = error.status || 500;
    console.error('[' + new Date().toISOString() + '] review_public error: ' + error.message);
    res.status(status).json({ error: error.message });
  }
});
'''

if "app.post('/api/review_public'" not in src:
    # 插到 /api/review 路由之后（找 /api/review 的收尾，或直接插在日志中间件前）
    ANCHOR = "app.use((req, res, next) => {"
    if ANCHOR not in src:
        print("ERROR: 找不到锚点"); sys.exit(1)
    idx = src.index(ANCHOR)
    src = src[:idx] + ROUTE + "\n" + src[idx:]
    print("+ 已插入 /api/review_public 路由（日志中间件前）")
else:
    print("= /api/review_public 已存在，跳过")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)
print("✓ server.js 写入完成")
