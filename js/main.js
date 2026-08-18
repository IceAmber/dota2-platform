/* ==========================================================================
   DOTA2 国服社区平台 · 前端逻辑（原生 JS，无任何依赖）
   --------------------------------------------------------------------------
   1. 通用：移动端导航、返回顶部、页脚年份
   2. report.html：读取 data/herostats.json 渲染三类榜单 + 认知差区块
   3. index.html：最新周报摘要
   所有数据来自同目录下相对路径 data/herostats.json（与脚本约定一致）。
   ========================================================================== */
(function () {
  'use strict';

  /* ---------------- 0. 常量与工具 ---------------- */

  var DATA_URL = 'data/herostats.json';      // 相对路径，与脚本输出一致

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // 千分位格式化（中文语境）
  function fmtNum(n) {
    if (n == null) return '—';
    return Number(n).toLocaleString('zh-CN');
  }

  // 胜率显示（含颜色分级：>=53 绿，>=50 金）
  function wrCell(wr) {
    if (wr == null) return '—';
    var cls = '';
    if (wr >= 53) cls = 'wr-high';
    else if (wr >= 50) cls = 'wr-mid';
    return '<span class="' + cls + '">' + wr.toFixed(2) + '%</span>';
  }

  // 排名徽章（前三名高亮）
  function rankBadge(rank) {
    if (rank == null) return '<span class="rank-badge">-</span>';
    var cls = rank === 1 ? ' rank-1' : rank === 2 ? ' rank-2' : rank === 3 ? ' rank-3' : '';
    return '<span class="rank-badge' + cls + '">' + rank + '</span>';
  }

  // 英雄头像（加载失败时用首字占位，避免破图）
  function heroImg(h, size) {
    size = size || 34;
    return '<img src="' + esc(h.img) + '" alt="' + esc(h.name) + '" loading="lazy" width="' +
      size + '" height="' + size + '" data-fb="' + esc(h.name) + '" data-size="' + size +
      '" onerror="if(!this.dataset.f){this.dataset.f=\'1\';this.outerHTML=window.fallbackBadge(this.dataset.fb,+this.dataset.size)}">';
  }

  window.fallbackBadge = function (name, size) {
    size = size || 34;
    var ch = (name || '?').trim().charAt(0) || '?';
    var radius = Math.round(size * 0.35);
    return '<span class="hero-badge-fallback" style="width:' + size + 'px;height:' + size +
      'px;border-radius:' + radius + 'px">' + esc(ch) + '</span>';
  };

  // 英雄单元格：头像 + 中文名 + 英文名
  function heroCell(h) {
    return '<div class="hero-cell">' + heroImg(h, 34) +
      '<div><span class="hc-name">' + esc(h.name) + '</span>' +
      '<span class="hc-en">' + esc(h.name_en) + '</span></div></div>';
  }

  // 通用表格渲染：headers = [{label, cls?}], cellsFn(h) -> [{html, cls?}]
  function renderTable(container, heroes, headers, cellsFn, limit) {
    var body = heroes.slice(0, limit).map(function (h) {
      var tds = cellsFn(h).map(function (c) {
        return '<td' + (c.cls ? ' class="' + c.cls + '"' : '') + '>' + c.html + '</td>';
      }).join('');
      return '<tr>' + tds + '</tr>';
    }).join('');
    var head = headers.map(function (x) {
      return '<th' + (x.cls ? ' class="' + x.cls + '"' : '') + '>' + x.label + '</th>';
    }).join('');
    container.innerHTML = '<div class="table-wrap"><table class="data-table">' +
      '<thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table></div>';
  }

  function showError(el, msg) {
    el.innerHTML = '<div class="data-state error"><span class="state-icon">⚠️</span>' +
      '数据加载失败，请检查网络或稍后重试。' +
      (msg ? '<br><small>' + esc(msg) + '</small>' : '') + '</div>';
  }

  /* ---------------- 1. 通用交互 ---------------- */

  // 移动端导航开关
  var navToggle = document.querySelector('.nav-toggle');
  var mainNav = document.querySelector('.main-nav');
  if (navToggle && mainNav) {
    navToggle.addEventListener('click', function () {
      mainNav.classList.toggle('open');
    });
    // 点击导航链接后自动收起
    mainNav.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') mainNav.classList.remove('open');
    });
  }

  // 返回顶部
  var backTop = document.getElementById('back-top');
  if (backTop) {
    window.addEventListener('scroll', function () {
      backTop.classList.toggle('show', window.scrollY > 300);
    }, { passive: true });
    backTop.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  // 页脚年份
  var yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  // 标记当前页导航高亮
  var path = location.pathname.split('/').pop() || 'index.html';
  var currentLink = document.querySelector('.main-nav a[href="' + path + '"]');
  if (currentLink) currentLink.classList.add('active');

  // 复制按钮（如"启动参数"）：点击复制 data-copy 内容
  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) { /* 忽略 */ }
    document.body.removeChild(ta);
  }
  document.querySelectorAll('.js-copy').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var text = btn.getAttribute('data-copy') || '';
      var done = function () {
        var original = btn.textContent;
        btn.textContent = '已复制 ✓';
        setTimeout(function () { btn.textContent = original; }, 1500);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); });
      } else {
        fallbackCopy(text);
        done();
      }
    });
  });

  /* ---------------- 2. 数据加载 ---------------- */

  function loadData() {
    if (location.protocol === 'file:') {
      // file:// 下 fetch 被浏览器拦截，提示用本地服务器
      return Promise.reject(new Error('file:// 打开时浏览器禁止读取本地 JSON，' +
        '请用本地服务器预览：python3 -m http.server 8080，然后访问 http://localhost:8080'));
    }
    return fetch(DATA_URL, { cache: 'no-cache' }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function (json) {
      if (!json || !Array.isArray(json.heroes) || json.heroes.length === 0) {
        throw new Error('数据为空或结构不正确');
      }
      return json;
    });
  }

  /* ---------------- 3. report.html ---------------- */

  function initReport() {
    var gapRoot = document.getElementById('gap-root');
    var winrateRoot = document.getElementById('winrate-root');
    var pickRoot = document.getElementById('pick-root');
    var proRoot = document.getElementById('pro-root');
    var metaEl = document.getElementById('data-meta');
    var topSelect = document.getElementById('top-n');
    if (!winrateRoot) return; // 非 report 页面

    function currentLimit() {
      var v = topSelect ? parseInt(topSelect.value, 10) : 10;
      return Number.isFinite(v) && v > 0 ? v : 10;
    }

    function renderAll(data) {
      var heroes = data.heroes;
      var byId = {};
      heroes.forEach(function (h) { byId[h.id] = h; });

      var limit = currentLimit();

      // —— 全分段胜率榜 ——
      var winrateList = heroes
        .filter(function (h) { return h.winrate_rank != null; })
        .sort(function (a, b) { return a.winrate_rank - b.winrate_rank; });
      renderTable(winrateRoot, winrateList, [
        { label: '排名' }, { label: '英雄' },
        { label: '胜率', cls: 'num' }, { label: '出场', cls: 'num' },
        { label: '出场率', cls: 'num' }, { label: '备注' }
      ], function (h) {
        return [
          { html: rankBadge(h.winrate_rank) },
          { html: heroCell(h) },
          { html: wrCell(h.pub_winrate), cls: 'num' },
          { html: fmtNum(h.pub_pick), cls: 'num' },
          { html: h.pick_share_pct != null ? h.pick_share_pct.toFixed(2) + '%' : '—', cls: 'num' },
          { html: h.is_gap ? '<span class="badge-gap">认知差</span>' : '' }
        ];
      }, limit);

      // —— 出场率榜 ——
      var pickList = heroes.slice().sort(function (a, b) { return a.pick_rank - b.pick_rank; });
      renderTable(pickRoot, pickList, [
        { label: '排名' }, { label: '英雄' },
        { label: '出场', cls: 'num' }, { label: '出场率', cls: 'num' },
        { label: '胜率', cls: 'num' }
      ], function (h) {
        return [
          { html: rankBadge(h.pick_rank) },
          { html: heroCell(h) },
          { html: fmtNum(h.pub_pick), cls: 'num' },
          { html: h.pick_share_pct != null ? h.pick_share_pct.toFixed(2) + '%' : '—', cls: 'num' },
          { html: wrCell(h.pub_winrate), cls: 'num' }
        ];
      }, limit);

      // —— 职业参考 ——
      var proList = heroes
        .filter(function (h) { return h.pro_rank != null; })
        .sort(function (a, b) { return a.pro_rank - b.pro_rank; });
      renderTable(proRoot, proList, [
        { label: '排名' }, { label: '英雄' },
        { label: '职业出场', cls: 'num' }, { label: '职业胜率', cls: 'num' },
        { label: '职业禁用', cls: 'num' }
      ], function (h) {
        return [
          { html: rankBadge(h.pro_rank) },
          { html: heroCell(h) },
          { html: fmtNum(h.pro_pick), cls: 'num' },
          { html: wrCell(h.pro_winrate), cls: 'num' },
          { html: fmtNum(h.pro_ban), cls: 'num' }
        ];
      }, limit);

      // —— 认知差区块 ——
      var gapList = (data.gap_ids || [])
        .map(function (id) { return byId[id]; })
        .filter(Boolean)
        .sort(function (a, b) { return a.winrate_rank - b.winrate_rank; });
      renderGap(gapRoot, gapList);

      // —— 数据元信息 ——
      if (metaEl) {
        metaEl.textContent = '数据时间：' + data.generated_at +
          ' · 全量 ' + data.summary.total_heroes + ' 英雄' +
          ' · 路人局样本 ' + fmtNum(data.total_pub_picks) + ' 场' +
          ' · 职业样本 ' + data.summary.pro_sample_heroes + ' 个英雄' +
          ' · 来源 ' + data.source_url;
      }
    }

    function renderGap(container, list) {
      if (!list.length) {
        container.innerHTML = '<div class="data-state">本期暂无满足条件的认知差英雄。</div>';
        return;
      }
      // 列表已按胜率排名升序，首个即本期最强的「认知差」英雄（highlights.top_gap_hero）
      var cards = list.map(function (h, i) {
        var reco = i === 0
          ? '<span class="badge-gap">本期最推荐</span>'
          : '';
        return '<div class="gap-card">' + heroImg(h, 52) +
          '<div>' +
          '<div class="gc-title">' + esc(h.name) + ' <span class="hc-en">' + esc(h.name_en) + '</span>' + reco + '</div>' +
          '<div class="gc-stats">' +
          '<span>路人胜率 <b>' + h.pub_winrate.toFixed(2) + '%</b></span>' +
          '<span>胜率排名 <b>#' + h.winrate_rank + '</b></span>' +
          '<span>出场排名 <b>#' + h.pick_rank + '</b></span>' +
          '</div>' +
          '<div class="gc-hint">胜率强但出场少 → 冷门强势，本周上分可试</div>' +
          '</div></div>';
      }).join('');
      container.innerHTML = '<div class="gap-grid">' + cards + '</div>';
    }

    // 顶部"显示条数"切换
    if (topSelect) {
      topSelect.addEventListener('change', function () {
        // 未加载完成时先不做任何事
        if (window.__reportData) renderAll(window.__reportData);
      });
    }

    var stateEl = document.getElementById('report-state');
    loadData().then(function (data) {
      window.__reportData = data;
      renderAll(data);
      if (stateEl) stateEl.innerHTML = '';   // 清掉顶部加载提示
    }).catch(function (err) {
      showError(winrateRoot, err.message);
      showError(pickRoot, '');
      showError(proRoot, '');
      showError(gapRoot, '');
      if (metaEl) metaEl.textContent = '数据加载失败，请稍后重试。';
      if (stateEl) stateEl.innerHTML = '<div class="data-state error"><span class="state-icon">⚠️</span>' +
        '数据加载失败，已保留历史数据可访问。<br><small>' + esc(err.message) + '</small></div>';
    });
  }

  /* ---------------- 4. index.html 周报摘要 ---------------- */

  // 首页「本期版本要点」：用 herostats.json 的 highlights 填充；缺失时友好降级，不抛错
  function renderTakeaway(el, highlights) {
    if (!el) return;
    var verEl = document.getElementById('tk-version');
    var gapEl = document.getElementById('tk-gap');
    var wrEl = document.getElementById('tk-winrate');
    var pickEl = document.getElementById('tk-pick');
    var banEl = document.getElementById('tk-ban');

    if (!highlights) {
      el.hidden = false;
      if (verEl) verEl.textContent = '';
      if (gapEl) gapEl.textContent = '本期版本要点数据暂缺，可查看完整周报。';
      if (wrEl) wrEl.textContent = '';
      if (pickEl) pickEl.textContent = '';
      if (banEl) banEl.hidden = true;
      return;
    }

    if (verEl) verEl.textContent = highlights.version_label ? '（' + highlights.version_label + '）' : '';

    // 版本心得：有「认知差」英雄则给推荐文案，否则跟胜率榜更稳
    var gap = highlights.top_gap_hero;
    if (gapEl) gapEl.textContent = gap
      ? '本期“认知差”推荐：' + gap.name + '——胜率 ' + Number(gap.winrate).toFixed(2) +
        '% 却很少有人玩，想上分可以试试。'
      : '本期无突出“认知差”英雄，跟胜率榜走更稳。';

    // 胜率之王
    var wr = highlights.top_winrate_hero;
    if (wrEl) wrEl.textContent = wr
      ? '全分段胜率最高：' + wr.name + '（' + Number(wr.winrate).toFixed(2) + '%）'
      : '全分段胜率数据暂缺。';

    // 最热英雄
    var pk = highlights.top_pick_hero;
    if (pickEl) pickEl.textContent = pk
      ? '大家都在玩：' + pk.name + '（出场 ' + fmtNum(pk.pick) + ' 场）'
      : '出场数据暂缺。';

    // 热门禁选（可选字段，无则隐藏）
    if (banEl) {
      if (highlights.hot_ban_hero) {
        banEl.textContent = '热门禁选：' + highlights.hot_ban_hero;
        banEl.hidden = false;
      } else {
        banEl.hidden = true;
      }
    }

    el.hidden = false;
  }

  function initIndex() {
    var root = document.getElementById('index-summary');
    var metaEl = document.getElementById('index-meta');
    if (!root) return; // 非首页

    var stateEl = document.getElementById('index-state');
    var statsEl = document.getElementById('index-stats');
    var tkEl = document.getElementById('index-takeaway');

    loadData().then(function (data) {
      var heroes = data.heroes;
      var topWr = heroes
        .filter(function (h) { return h.winrate_rank != null; })
        .sort(function (a, b) { return a.winrate_rank - b.winrate_rank; })
        .slice(0, 5);
      var topPick = heroes.slice().sort(function (a, b) { return a.pick_rank - b.pick_rank; })
        .slice(0, 5);
      var gap = (data.gap_ids || []).length;

      // 统计卡片（英雄总数 / 认知差英雄 可点击跳转到对应榜单区块）
      if (statsEl) statsEl.innerHTML = '<div class="stat-row">' +
        '<a class="stat-card stat-link" href="report.html#winrate-section"><div class="stat-num">' + data.summary.total_heroes +
        '</div><div class="stat-label">英雄总数 ›</div></a>' +
        '<div class="stat-card"><div class="stat-num">' + fmtNum(data.total_pub_picks) +
        '</div><div class="stat-label">路人局出场</div></div>' +
        '<a class="stat-card stat-link" href="report.html#gap-section"><div class="stat-num">' + gap +
        '</div><div class="stat-label">认知差英雄 ›</div></a>' +
        '<div class="stat-card"><div class="stat-num">' + data.data_date +
        '</div><div class="stat-label">数据日期</div></div>' +
        '</div>' +

        '<div class="card-grid" style="grid-template-columns:1fr 1fr">' +
        '<div class="card"><h3>🏆 路人胜率 TOP5</h3><table class="data-table" style="min-width:0">' +
        topWr.map(function (h) {
          return '<tr><td>' + rankBadge(h.winrate_rank) + '</td><td>' + heroCell(h) +
            '</td><td class="num">' + wrCell(h.pub_winrate) + '</td></tr>';
        }).join('') + '</table></div>' +
        '<div class="card"><h3>🔥 出场率 TOP5</h3><table class="data-table" style="min-width:0">' +
        topPick.map(function (h) {
          return '<tr><td>' + rankBadge(h.pick_rank) + '</td><td>' + heroCell(h) +
            '</td><td class="num">' + fmtNum(h.pub_pick) + '</td></tr>';
        }).join('') + '</table></div>' +
        '</div>' +
        '<p style="margin-top:14px"><a class="btn btn-sm btn-primary" href="report.html">查看完整周报 →</a></p>';

      // 本期版本要点
      renderTakeaway(tkEl, data.highlights);

      if (stateEl) stateEl.innerHTML = '';
      if (metaEl) metaEl.textContent = '周报摘要 · 数据来源 OpenDota，更新于 ' + data.generated_at;
    }).catch(function (err) {
      // 数据不可用时替换为静态占位提示，速报区块也给出友好占位
      if (stateEl) stateEl.innerHTML = '<div class="data-state"><span class="state-icon">📡</span>' +
        '周报数据暂不可用（' + esc(err.message) + '）。<br>首页为静态占位，点击「版本周报」查看历史数据。</div>';
      if (statsEl) statsEl.innerHTML = '';
      if (tkEl) {
        tkEl.hidden = false;
        tkEl.innerHTML = '<h3>📌 本期版本速报</h3>' +
          '<p>周报数据暂不可用，本期版本要点暂无。</p>';
      }
      if (metaEl) metaEl.textContent = '';
    });
  }

  /* ---------------- 4.5 分享 / 二维码 ---------------- */
  /* 纯前端分享工具条。二维码用自托管的开源库 qrcode.js（MIT，kazuhikoarase），
     本地文件无外部 CDN 依赖。 */

  function initShare() {
    var bar = document.querySelector('.share-bar');
    if (!bar) return;
    var url = window.location.href;

    // 下载图片：新窗口打开周报长图，用户可另存
    var dl = bar.querySelector('.js-share-dl');
    if (dl) dl.addEventListener('click', function () {
      window.open('data/weekly_report.png', '_blank');
    });

    // 复制链接
    var cp = bar.querySelector('.js-share-copy');
    if (cp) cp.addEventListener('click', function () {
      var done = function () {
        cp.textContent = '\u2713 已复制';
        setTimeout(function () { cp.textContent = '复制链接'; }, 1500);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(done, function () { fallbackCopy(url); done(); });
      } else { fallbackCopy(url); done(); }
    });

    // 手机原生分享（navigator.share），桌面不支持则隐藏
    var sh = bar.querySelector('.js-share-native');
    if (sh) {
      if (navigator.share) {
        sh.style.display = '';
        sh.addEventListener('click', function () {
          navigator.share({ title: document.title, url: url }).catch(function () {});
        });
      } else {
        sh.style.display = 'none';
      }
    }

    // 二维码弹层
    var qrBtn = bar.querySelector('.js-share-qr');
    var overlay = document.getElementById('qr-overlay');
    if (qrBtn && overlay) {
      qrBtn.addEventListener('click', function () {
        overlay.classList.add('open');
        var host = document.getElementById('qr-canvas');
        if (host && !host.dataset.done) {
          host.dataset.done = '1';
          try {
            var qr = qrcode(0, 'L');   // 全局 qrcode 由 vendor/qrcode.js 提供
            qr.addData(url);
            qr.make();
            renderQR(host, qr, 6);
          } catch (err) {
            host.parentNode.insertAdjacentHTML('beforeend',
              '<p class="qr-note">二维码生成失败，请直接复制链接分享。</p>');
          }
        }
      });
      var close = overlay.querySelector('.qr-close');
      if (close) close.addEventListener('click', function () { overlay.classList.remove('open'); });
      overlay.addEventListener('click', function (e) { if (e.target === overlay) overlay.classList.remove('open'); });
    }
  }

  // 把 qrcode 库的矩阵画到 canvas
  function renderQR(canvas, qr, scale) {
    var n = qr.getModuleCount();
    canvas.width = n * scale; canvas.height = n * scale;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#000';
    for (var y = 0; y < n; y++) for (var x = 0; x < n; x++) {
      if (qr.isDark(y, x)) ctx.fillRect(x * scale, y * scale, scale, scale);
    }
  }

  /* ---------------- 5. 启动 ---------------- */
  document.addEventListener('DOMContentLoaded', function () {
    initReport();
    initIndex();
    initShare();
  });
})();
