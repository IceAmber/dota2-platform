#!/usr/bin/env python3
# 在 ai-launcher-backend/server.js 中插入 /api/review 路由（幂等，可重复执行）
import re, sys

PATH = "/opt/ai-launcher-backend/server.js"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

# 1) 插入 require
REQ = "const review = require('./review');\n"
if "require('./review')" not in src:
    anchor = "const app = express();"
    if anchor not in src:
        print("ERROR: 找不到 require 插入锚点"); sys.exit(1)
    src = src.replace(anchor, anchor + "\n" + REQ, 1)
    print("+ 已插入 require('./review')")

# 2) 插入 /api/review 路由（在日志中间件 app.use((req,res,next) => 之前）
ROUTE = '''
app.post('/api/review', authMiddleware, async (req, res) => {
  try {
    const ctx = { fetch, LLM_URL, LLM_MODEL, LLM_API_KEY, USE_DEEPSEEK };
    const result = await review.runReview(ctx, req.body);
    const now = new Date().toISOString();
    console.log('[' + now + '] review OK, provider=' + result.provider + ' model=' + result.model + ' len=' + result.review.length);
    res.json(result);
  } catch (error) {
    const status = error.status || 500;
    console.error('[' + new Date().toISOString() + '] review error: ' + error.message);
    res.status(status).json({ error: error.message });
  }
});
'''
if "app.post('/api/review'" not in src:
    LOG_ANCHOR = "app.use((req, res, next) => {"
    if LOG_ANCHOR not in src:
        print("ERROR: 找不到日志中间件锚点"); sys.exit(1)
    # 找到日志中间件那行的行首位置，在其前插入
    idx = src.index(LOG_ANCHOR)
    src = src[:idx] + ROUTE + "\n" + src[idx:]
    print("+ 已插入 /api/review 路由（日志中间件之前）")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)
print("✓ server.js 写入完成")
