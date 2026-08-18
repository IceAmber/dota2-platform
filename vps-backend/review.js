// 赛后复盘 LLM 路由（复用 ai-launcher-backend 的 LLM/鉴权/限流）
// 用法：POST /api/review
//  body: { matchData?: object|string, customPrompt?: string }
//   - matchData  : 比赛结构化数据（OpenDota matches 或人工整理的摘要）。缺省时走「战术/版本分析」模式
//   - customPrompt: 可选的额外说明（如"重点讲XX队的中单发挥"）
// 返回: { review: "markdown 复盘文本", provider, model }

const BASE_SYSTEM = `你是一名资深的 DOTA2 赛事复盘分析师。请基于给出的比赛数据，产出一份专业、有观点、数据驱动、适合中文社区分享的赛后复盘。

严格规则（务必遵守）：
1. 只能依赖给定数据中出现的数字和事实，绝不允许编造或臆测不存在的比分、选手表现、装备、时间点。数据里没有的就明确写"数据未提供"。
2. 用 markdown 格式输出，结构固定包含以下小节（用中文标题）：
   ## 一、战报概览
   ## 二、关键选手表现（MVP 提名）
   ## 三、比赛转折点分析
   ## 四、数据亮点与解读
   ## 五、阵容与版本观察
   ## 六、一句话总结
3. MVP 提必须基于数据里的客观指标（伤害/GPM/XPM/KDA/参战率等），并标注依据。
4. 若数据缺失某些维度，诚实标注，不要强行虚构。
5. 语气专业但易读，面向 DOTA2 玩家，可适度用圈内术语。`;

module.exports = {
  // 组装系统 + 用户消息，返回 messages 数组
  buildMessages(matchData, customPrompt) {
    const dataText = typeof matchData === 'string'
      ? matchData
      : (matchData ? JSON.stringify(matchData, null, 2) : '');
    let user = '比赛数据：\n```\n' + (dataText || '(无结构化数据，请基于你对该版本和经典阵容的理解做战术层面分析，并明确说明这是战术推演而非本场实录)') + '\n```\n请输出复盘。';
    if (customPrompt) user = customPrompt + '\n\n' + user;
    return [
      { role: 'system', content: BASE_SYSTEM },
      { role: 'user', content: user }
    ];
  },

  // 实际调 LLM（复用与 /api/chat 相同的调用方式；由调用方注入依赖以便共享配置）
  async runReview(ctx, reqBody) {
    const { matchData, customPrompt } = reqBody || {};
    const messages = this.buildMessages(matchData, customPrompt);
    const response = await ctx.fetch(ctx.LLM_URL + '/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + ctx.LLM_API_KEY,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: ctx.LLM_MODEL,
        messages,
        temperature: 0.8,
        top_p: 0.9,
        max_tokens: 2048
      })
    });
    if (!response.ok) {
      const errorText = await response.text();
      const err = new Error('LLM API error: ' + errorText);
      err.status = response.status;
      throw err;
    }
    const data = await response.json();
    const review = (data && data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content) || '';
    return { review, provider: ctx.USE_DEEPSEEK ? 'DeepSeek' : 'Qwen', model: ctx.LLM_MODEL };
  }
};
