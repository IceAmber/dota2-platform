// server.js 补丁：新增赛后复盘路由 /api/review
// 应用位置：
//   1) 顶部 require 后加：const review = require('./review');
//   2) app.post('/api/chat'...) 之后、app.use((req,res,next)=>日志) 之前插入 /api/review 路由
//   3) 保持不变的其他部分

// ---- 第 1 处：require ----
const review = require('./review');

// ---- 第 2 处：在 /api/chat 路由之后插入 ----
app.post('/api/review', authMiddleware, async (req, res) => {
  try {
    const ctx = {
      fetch,
      LLM_URL,
      LLM_MODEL,
      LLM_API_KEY,
      USE_DEEPSEEK
    };
    const result = await review.runReview(ctx, req.body);
    console.log('[' + new Date().toISOString() + '] review OK, provider=' + result.provider + ' model=' + result.model + ' len=' + result.review.length);
    res.json(result);
  } catch (error) {
    const status = error.status || 500;
    console.error('[' + new Date().toISOString() + '] review error: ' + error.message);
    res.status(status).json({ error: error.message });
  }
});
