/* 旅迹 LVJI · 一日行程前端 */
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const yuan = n => '¥' + Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 });

const state = { tags: [], interests: [], time: null, access: [], data: null, group: 'A' };

/* ── chips ── */
document.querySelectorAll('.chip-group').forEach(g => {
  const key = g.dataset.group;
  g.querySelectorAll('.chip').forEach(btn => {
    btn.onclick = () => {
      const v = btn.dataset.value;
      if (key === 'time') {
        const was = btn.classList.contains('on');
        g.querySelectorAll('.chip').forEach(x => x.classList.remove('on'));
        state.time = was ? null : v;
        if (!was) btn.classList.add('on');
        return;
      }
      if (key === 'access') {
        btn.classList.toggle('on');
        state.access = [...g.querySelectorAll('.chip.on')].map(x => x.dataset.value);
        return;
      }
      btn.classList.toggle('on');
      state[key] = [...g.querySelectorAll('.chip.on')].map(x => x.dataset.value);
    };
  });
});

/* ── 数据集信息 ── */
fetch('api/meta').then(r => r.json()).then(m => {
  $('dataPill').textContent = `本地数据集 ${m.version} · ${m.spots} 景点 / ${m.hotels} 住宿`;
  $('datasetMeta').textContent = `${m.city} · ${m.source.slice(0, 14)}…`;
  $('dataset').innerHTML = [
    ['spots', m.spots, '景点'], ['food', m.food, '餐厅'], ['hotels', m.hotels, '住宿样例'],
    ['weatherDays', m.weatherDays, '天气样例'],
  ].map(([k, v, label]) => `<div class="ds-cell"><b>${v}</b><small>${label}</small></div>`).join('') +
    `<p class="ds-note">来源：${esc(m.source)}　版本 ${esc(m.version)}　生成日 ${esc(m.today)}</p>`;
}).catch(() => { $('dataPill').textContent = '本地数据集未加载'; });

/* ── 提交 ── */
function form() {
  const f = {};
  if (state.tags.length) f.tags = state.tags.join(',');
  if (state.interests.length) f.interests = state.interests.join(',');
  if (state.access.includes('1')) f.wheelchair = '1';
  if (state.time === 'half') { f.start = '09:00'; f.end = '13:30'; }
  if (state.time === 'night') { f.end = '21:00'; }
  return f;
}

async function run(opt) {
  const scroll = !opt || opt.scroll !== false;
  const text = $('ask').value.trim();
  if (text.length < 2) { $('ask').focus(); return; }
  const btn = $('planBtn');
  btn.disabled = true; btn.textContent = '正在排程…';
  $('result').hidden = false;
  $('summary').innerHTML = '<div class="skeleton"></div>';
  $('timeline').innerHTML = ''; $('map').innerHTML = ''; $('budget').innerHTML = '';
  try {
    const r = await fetch('api/plan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, form: form() })
    });
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    state.data = data;
    state.group = data.groups[0].id;
    render();
    if (scroll) $('result').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    $('summary').innerHTML = `<h2>没能排出来</h2><p class="lede">${esc(e.message)}</p>`;
  } finally {
    btn.disabled = false; btn.textContent = '生成一天行程';
  }
}
$('planBtn').onclick = () => run();
$('ask').onkeydown = e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') run(); };
$('demoBtn').onclick = () => {
  $('ask').value = '明天带坐轮椅的奶奶和两个孩子去杭州玩一天，想看西湖和博物馆，晚上想吃点小吃';
  run();
};
$('resetBtn').onclick = () => {
  $('result').hidden = true; $('ask').value = ''; $('ask').focus();
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

/* ── 渲染 ── */
function render() {
  const d = state.data;
  renderSummary(d);
  renderDecisions(d);
  renderTabs(d);
  renderTimeline(d);
  renderMap(d);
  renderBudget(d);
  renderAccess(d);
  renderFactors(d);
  renderOpt(d);
  renderApi(d);
  $('mapMeta').textContent = `${d.route.points.length} 个停留点 · 经纬度等比投影`;
}

function renderSummary(d) {
  const q = d.request, w = d.weather;
  const wx = `${w.condition} ${w.low}–${w.high}℃ · 降水 ${w.rainProb}%`;
  $('summary').innerHTML = `
    <div class="summary">
      <div class="summary-route"><h2>${esc(q.city)} · 一天安排</h2></div>
      <div class="summary-meta">
        <span class="meta-pill">${esc(q.date)} ${esc(q.weekday)}</span>
        <span class="meta-pill">${q.people} 人${q.flags.length ? ' · ' + esc(q.flags.map(f => ({ elderly: '含长辈', kids: '含孩子', couple: '情侣', friends: '朋友同行' }[f] || f)).join('/')) : ''}</span>
        <span class="meta-pill">${esc(q.start)}–${esc(q.end)}</span>
        <span class="meta-pill wx">${esc(wx)}</span>
        ${q.wheelchair ? '<span class="meta-pill warn">轮椅可达</span>' : ''}
        ${q.lowWalk ? '<span class="meta-pill warn">低步行</span>' : ''}
      </div>
    </div>`;
}

function renderDecisions(d) {
  $('decisions').innerHTML = (d.decisions || []).map(x =>
    `<div class="dec ${x.level}"><b>${esc(x.title)}</b><span>${esc(x.text)}</span></div>`).join('');
}

function renderTabs(d) {
  const tabs = $('groupTabs');
  if (d.groups.length === 1) { tabs.innerHTML = ''; return; }
  tabs.innerHTML = d.groups.map(g =>
    `<button class="group-tab ${g.id === state.group ? 'on' : ''}" data-g="${g.id}">
      <b>${esc(g.name)} · ${g.members} 人</b><small>${esc(g.profile)} · ${g.stats.spots} 个点</small>
    </button>`).join('');
  tabs.querySelectorAll('[data-g]').forEach(b => b.onclick = () => {
    state.group = b.dataset.g; renderTabs(d); renderTimeline(d); renderAccess(d); renderFactors(d); renderOpt(d);
  });
}

const ICON = {
  spot: '●', meal: '餐', travel: '→', wait: '等', rest: '息'
};

function renderTimeline(d) {
  const g = d.groups.find(x => x.id === state.group) || d.groups[0];
  $('timelineTitle').textContent = `${g.name} · 一天时间轴`;
  $('timelineMeta').textContent = `${g.stats.spots} 个停留点 · 排队 ${g.stats.queueMin} 分钟 · 步行 ${g.stats.walkKm} 公里`;
  let seq = 0;
  $('timeline').innerHTML = g.timeline.map(x => {
    const isSpot = x.type === 'spot';
    if (isSpot) seq += 1;
    const dot = isSpot ? String(seq) : ICON[x.type] || '·';
    const tags = [];
    if (isSpot) {
      tags.push(x.ticket ? `<span class="tag queue">门票 ${yuan(x.ticket)}</span>` : '<span class="tag free">免费</span>');
      if (x.queue) tags.push(`<span class="tag queue">排队 ${x.queue} 分钟</span>`);
      tags.push(`<span class="tag">步行强度 ${x.walkIntensity}/5</span>`);
      tags.push(x.indoor ? '<span class="tag rain">室内</span>' : '<span class="tag">户外</span>');
      if (x.access.wheelchair) tags.push('<span class="tag acc">轮椅可达</span>');
      if (x.access.toilet) tags.push('<span class="tag acc">无障碍厕所</span>');
      if (x.access.aed) tags.push('<span class="tag acc">AED</span>');
      if (x.access.parking) tags.push('<span class="tag acc">停车位</span>');
    } else if (x.type === 'meal') {
      tags.push(`<span class="tag queue">排队 ${x.queue} 分钟</span>`);
      tags.push(`<span class="tag">人均 ${yuan(x.price)}</span>`);
    } else if (x.type === 'travel') {
      tags.push(`<span class="tag">${esc(x.mode)}</span>`);
      if (x.km) tags.push(`<span class="tag">${x.km} 公里</span>`);
    }
    return `<div class="tl-item ${x.type}">
      <div class="tl-time"><b>${esc(x.start)}</b>${esc(x.end)}</div>
      <div class="tl-rail"><span class="tl-dot">${dot}</span></div>
      <div class="tl-body">
        <div class="tl-title">${esc(x.name)}${isSpot && x.score != null ? `<span class="score-badge">${(Math.round(x.score * 10) / 10).toFixed(1)}</span>` : ''}</div>
        ${x.reason ? `<div class="tl-why">${esc(x.reason)}</div>` : ''}
        ${tags.length ? `<div class="tl-tags">${tags.join('')}</div>` : ''}
      </div>
    </div>`;
  }).join('');
}

/* ── 路线示意（SVG，等比投影） ── */
function renderMap(d) {
  const pts = d.route.points || [];
  const hotel = d.hotel;
  const all = pts.concat([{ lat: hotel.lat, lon: hotel.lon }]);
  const lats = all.map(p => p.lat), lons = all.map(p => p.lon);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const minLon = Math.min(...lons), maxLon = Math.max(...lons);
  const W = 460, H = 320, pad = 42;
  const sx = v => pad + (maxLon === minLon ? .5 : (v - minLon) / (maxLon - minLon)) * (W - pad * 2);
  const sy = v => pad + (maxLat === minLat ? .5 : 1 - (v - minLat) / (maxLat - minLat)) * (H - pad * 2);

  const colors = { A: '#0C3B3C', B: '#D8623B' };
  let paths = '';
  d.groups.forEach(g => {
    const gp = pts.filter(p => p.group === g.id).sort((a, b) => a.seq - b.seq);
    if (!gp.length) return;
    const line = [[hotel.lat, hotel.lon]].concat(gp.map(p => [p.lat, p.lon])).concat([[hotel.lat, hotel.lon]]);
    const dd = line.map(([la, lo], i) => `${i ? 'L' : 'M'}${sx(lo).toFixed(1)} ${sy(la).toFixed(1)}`).join(' ');
    paths += `<path d="${dd}" fill="none" stroke="${colors[g.id]}" stroke-width="${g.id === state.group ? 2.4 : 1.4}"
      stroke-dasharray="${g.id === 'B' ? '6 5' : '0'}" opacity="${g.id === state.group ? .95 : .4}" stroke-linejoin="round"/>`;
  });

  let nodes = `<circle cx="${sx(hotel.lon)}" cy="${sy(hotel.lat)}" r="6" fill="#fff" stroke="#12211F" stroke-width="2"/>
    <text x="${sx(hotel.lon) + 9}" y="${sy(hotel.lat) + 4}" font-size="10" fill="#435B57">酒店</text>`;

  // 地图上只放编号，名称与时间放到下方清单，避免密集点位标签互相压字
  d.groups.forEach(g => {
    const gp = pts.filter(p => p.group === g.id).sort((a, b) => a.seq - b.seq);
    gp.forEach(p => {
      const on = g.id === state.group;
      nodes += `<g opacity="${on ? 1 : .32}">
        <circle cx="${sx(p.lon)}" cy="${sy(p.lat)}" r="${on ? 12 : 9}" fill="${colors[g.id]}" stroke="#fff" stroke-width="2"/>
        <text x="${sx(p.lon)}" y="${sy(p.lat) + 4}" text-anchor="middle" font-size="${on ? 11.5 : 9.5}" font-weight="700" fill="#fff">${p.seq}</text>
      </g>`;
    });
  });

  // 网格底纹
  let grid = '';
  for (let i = 1; i < 5; i++) {
    grid += `<line x1="${(W / 5) * i}" y1="0" x2="${(W / 5) * i}" y2="${H}" stroke="#E4DCD0" stroke-width=".6"/>`;
    grid += `<line x1="0" y1="${(H / 5) * i}" x2="${W}" y2="${(H / 5) * i}" stroke="#E4DCD0" stroke-width=".6"/>`;
  }

  $('map').innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="路线示意图">${grid}${paths}${nodes}</svg>`;
  const active = d.groups.find(g => g.id === state.group) || d.groups[0];
  const list = pts.filter(p => p.group === active.id).sort((a, b) => a.seq - b.seq)
    .map(p => `<li><b>${p.seq}</b><span>${esc(p.name)}</span><em>${esc(p.start)}</em></li>`).join('');
  $('mapLegend').innerHTML =
    (d.groups.length > 1
      ? `<div class="legend-groups">${d.groups.map(g => `<span><i style="background:${colors[g.id]}"></i>${esc(g.name)}（${g.members} 人）</span>`).join('')}</div>`
      : `<div class="legend-groups"><span><i style="background:#0C3B3C"></i>当天动线，数字为到访顺序</span></div>`) +
    `<ol class="map-list">${list}</ol>`;
}

function renderBudget(d) {
  const b = d.budget;
  const rows = [
    ['门票', b.ticket], ['市内交通', b.localFare], ['餐饮', b.meals], ['住宿 1 晚', b.hotel],
  ];
  if (b.intercityTotal) rows.push([`城际（${b.intercity.map(x => x.code).join(' / ')}）`, b.intercityTotal]);
  $('budget').innerHTML = rows.map(([k, v]) =>
    `<div class="budget-row"><span>${esc(k)}</span><b>${yuan(v)}</b></div>`).join('') +
    `<div class="budget-total"><div><small>${d.request.people} 人合计</small><div class="num">${yuan(b.total)}</div></div>
      <div style="text-align:right"><small>人均</small><div style="font-weight:600">${yuan(b.perPerson)}</div></div></div>
     <p class="budget-per">按本地样例价估算，不含购物与临时打车溢价</p>`;
  $('budgetMeta').textContent = d.hotel.name;
}

function renderAccess(d) {
  const g = d.groups.find(x => x.id === state.group) || d.groups[0];
  const spots = g.timeline.filter(x => x.type === 'spot');
  if (!spots.length) { $('access').innerHTML = '<p class="empty">这条路线没有停留点</p>'; return; }
  $('access').innerHTML = `<div class="acc-list">${spots.map(x => {
    const f = (k, label) => `<span class="acc-flag ${x.access[k] ? '' : 'off'}">${label}</span>`;
    return `<div class="acc-item"><b>${esc(x.name)}</b>
      <div class="acc-flags">
        ${f('wheelchair', '轮椅可达')}${f('toilet', '无障碍厕所')}${f('aed', 'AED')}${f('parking', '停车位')}
        <span class="acc-flag ${x.walkIntensity <= 3 ? '' : 'off'}">步行强度 ${x.walkIntensity}/5</span>
      </div></div>`;
  }).join('')}</div>`;
}

function renderApi(d) {
  const calls = d.apiCalls || [];
  const total = calls.reduce((s, c) => s + c.ms, 0);
  $('apiMeta').textContent = `${calls.length} 次调用 · 合计 ${total} ms`;
  $('apiLog').innerHTML = calls.map(c =>
    `<div class="api-row"><code>${esc(c.api)}</code><span class="rows">${c.rows} 行</span><span class="ms">${c.ms} ms</span></div>`).join('') +
    `<p class="ds-note">以上为本地 mock API 的真实调用记录，行程全部来自这些返回，没有任何预置文案。</p>`;
}

/* ── 影响因素与评分分解 ── */
const KIND_CLS = { '定量': 'k-quant', '半定量': 'k-semi', '定性': 'k-qual' };

function renderFactors(d) {
  const crit = d.criteria || [];
  if (!crit.length) return;
  const g = d.groups.find(x => x.id === state.group) || d.groups[0];
  const spots = g.timeline.filter(x => x.type === 'spot');
  const maxAbs = Math.max(9, ...spots.flatMap(s => crit.map(c => Math.abs((s.parts || {})[c.key] || 0))));

  $('factorsMeta').textContent = `${crit.length} 个维度 · ${g.name} ${spots.length} 个停留点`;

  /* 维度图例：权重 + 定量/半定量/定性 */
  const wTxt = w => (w >= 1 ? String(w) : '1/' + Math.round(1 / w));
  $('critLegend').innerHTML = crit.map(c => `
    <div class="crit-chip ${KIND_CLS[c.kind] || ''}">
      <span class="crit-kind">${esc(c.kind)}</span>
      <b>${esc(c.label)}</b>
      <span class="crit-w">权重 ${wTxt(c.weight)}</span>
    </div>`).join('');

  /* 评分矩阵 */
  const head = `<thead><tr><th class="mx-name">停留点</th>
    ${crit.map(c => `<th class="${KIND_CLS[c.kind] || ''}"><span>${esc(c.label)}</span><small>${esc(c.kind)}</small></th>`).join('')}
    <th class="mx-total">合计</th></tr></thead>`;

  const sev = v => {
    const a = Math.min(1, Math.abs(v) / maxAbs);
    return Math.round((0.05 + a * 0.34) * 100) / 100;
  };

  const body = `<tbody>${spots.map(s => {
    const p = s.parts || {};
    const cells = crit.map(c => {
      const v = p[c.key] || 0;
      const bg = Math.abs(v) < 0.01 ? 'var(--surface-2)'
        : v > 0 ? `rgba(12,59,60,${sev(v)})` : `rgba(216,98,59,${sev(v)})`;
      const txt = Math.abs(v) < 0.01 ? '—' : (v > 0 ? '+' : '') + (Math.round(v * 10) / 10);
      return `<td class="mx-cell" style="background:${bg}">${txt}</td>`;
    }).join('');
    return `<tr><th class="mx-name">${esc(s.name)}</th>${cells}
      <td class="mx-total">${(Math.round((s.score || 0) * 10) / 10).toFixed(1)}</td></tr>`;
  }).join('')}</tbody>`;

  $('scoreMatrix').innerHTML = head + body;

  /* 落选归因 */
  const rj = d.rejected || [];
  $('rejected').innerHTML = rj.length ? rj.map(x => `
    <div class="rj ${x.kind}">
      <div class="rj-head"><b>${esc(x.name)}</b>
        <span class="rj-kind">${x.kind === 'blocked' ? '硬约束出局' : '评分未入选'}</span></div>
      <div class="rj-why">${x.kind === 'blocked' ? esc(x.why) : esc(x.why) + (x.score != null ? `　合计 ${(Math.round(x.score * 10) / 10).toFixed(1)}` : '')}</div>
    </div>`).join('') : '<p class="empty">所有候选点都排进去了</p>';
}

/* ── 求解过程：构造 vs 最优 + 收敛曲线 ── */
function renderOpt(d) {
  const g = d.groups.find(x => x.id === state.group) || d.groups[0];
  const o = g.optimize;
  if (!o) { $('optChart').innerHTML = ''; $('optKv').innerHTML = ''; return; }
  const trace = o.trace || [];
  $('optMeta').textContent = `${o.iters} 轮 · 接受改进 ${o.accepted || 0} 次`;

  const W = 440, H = 148, padL = 30, padB = 18, padT = 8;
  const vals = trace.map(t => t[1]);
  const minV = Math.min(...vals), maxV = Math.max(...vals);
  const span = Math.max(maxV - minV, 0.001);
  const sx = i => padL + (trace.length < 2 ? 0 : i / (trace.length - 1)) * (W - padL - 4);
  const sy = v => padT + (1 - (v - minV) / span) * (H - padT - padB);

  const pts = trace.map((t, i) => `${sx(i).toFixed(1)} ${sy(t[1]).toFixed(1)}`).join(' L');
  const area = `M${sx(0).toFixed(1)} ${(H - padB).toFixed(1)} L${pts} L${sx(trace.length - 1).toFixed(1)} ${(H - padB).toFixed(1)} Z`;

  $('optChart').innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="收敛曲线">
    <defs><linearGradient id="og" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0C3B3C" stop-opacity=".18"/>
      <stop offset="1" stop-color="#0C3B3C" stop-opacity="0"/>
    </linearGradient></defs>
    ${[0, .5, 1].map(k => `<line x1="${padL}" y1="${(padT + k * (H - padT - padB)).toFixed(1)}" x2="${W - 4}" y2="${(padT + k * (H - padT - padB)).toFixed(1)}" stroke="#E4DCD0" stroke-width=".7"/>`).join('')}
    <path d="${area}" fill="url(#og)"/>
    <path d="M${pts}" fill="none" stroke="#0C3B3C" stroke-width="1.8" stroke-linejoin="round"/>
    <circle cx="${sx(trace.length - 1).toFixed(1)}" cy="${sy(maxV).toFixed(1)}" r="3.2" fill="#D8623B"/>
    <text x="0" y="${(sy(maxV) + 3).toFixed(1)}" font-size="9" fill="#7C918D">${maxV.toFixed(1)}</text>
    <text x="0" y="${(sy(minV) + 3).toFixed(1)}" font-size="9" fill="#7C918D">${minV.toFixed(1)}</text>
    <text x="${padL}" y="${H - 5}" font-size="9" fill="#7C918D">0</text>
    <text x="${W - 4}" y="${H - 5}" text-anchor="end" font-size="9" fill="#7C918D">${o.iters}</text>
  </svg>`;

  const up = o.gain > 0;
  $('optKv').innerHTML = `
    <div class="kv"><span>贪心构造</span><b>${o.base.toFixed(1)}</b></div>
    <div class="kv"><span>ILS 最优</span><b class="hi">${o.best.toFixed(1)}</b></div>
    <div class="kv"><span>提升</span><b class="${up ? 'up' : ''}">${up ? '+' : ''}${o.gain.toFixed(1)}${o.base ? `（${(o.gain / Math.abs(o.base) * 100).toFixed(1)}%）` : ''}</b></div>
    <div class="kv"><span>改进轮次</span><b>${o.rounds || 0} / ${o.iters}</b></div>`;
  $('optNote').textContent = up
    ? `贪心构造拿到 ${o.base.toFixed(1)} 分，经 ${o.iters} 轮邻域搜索后提升到 ${o.best.toFixed(1)} 分。曲线为阶梯状——只有找到更优解才会跳升。`
    : `本次需求下贪心构造已经是最优，${o.iters} 轮搜索没有找到更好的顺序。`;
}

/* 最优性验证：小规模全排列穷举，与 ILS 结果对比 */
$('verifyBtn').onclick = async () => {
  const btn = $('verifyBtn');
  btn.disabled = true; btn.textContent = '验证中…';
  $('verifyOut').innerHTML = '<p class="opt-note">正在穷举全部排列并与 ILS 结果对比…</p>';
  try {
    const [real, sc] = await Promise.all([
      fetch('api/benchmark').then(r => r.json()),
      fetch('api/scaling').then(r => r.json())
    ]);
    const s = real.summary || {};
    const rows = sc.rows || [];
    const r0 = rows[0], rN = rows[rows.length - 1];
    const tail = (r0 && rN) ? (() => {
      const permX = Math.round(rN.perms / r0.perms);
      const bruteX = Math.round(rN.bruteMs / r0.bruteMs);
      const ilsX = (rN.ilsMs / r0.ilsMs).toFixed(1);
      const maxGap = Math.max(...rows.map(x => x.gapPct)).toFixed(2);
      return `规模从 n=${r0.n} 增到 n=${rN.n}，排列数涨 ${permX.toLocaleString('zh-CN')} 倍，穷举耗时涨 ${bruteX.toLocaleString('zh-CN')} 倍；ILS 只从 ${r0.ilsMs} ms 涨到 ${rN.ilsMs} ms（${ilsX} 倍）。gap 是相对穷举最优的差距，全程不超过 ${maxGap}%。n≤5 时穷举本来更快，规模上去后启发式才反超——这条交叉点就是它的适用边界。`;
    })() : '';
    $('verifyOut').innerHTML = `
      <div class="vf-head">
        <b>真实景点算例</b>
        <span>${s.trips} 组 · 每组 ${s.perms} 种排列全穷举 · 命中最优 ${s.hit}/${s.trips}（${s.hitRate}%）· 平均 gap ${s.avgGap}%</span>
      </div>
      <div class="vf-table">
        <div class="vf-row vf-th"><span>规模</span><span>排列数</span><span>全穷举</span><span>ILS</span><span>gap</span><span>加速</span></div>
        ${rows.map(x => `<div class="vf-row">
          <span>n=${x.n}</span><span>${x.perms.toLocaleString('zh-CN')}</span>
          <span>${x.bruteMs} ms</span><span>${x.ilsMs} ms</span>
          <span class="${x.gapPct <= 0.5 ? 'ok' : ''}">${x.gapPct}%</span>
          <span>${x.speedup}×</span></div>`).join('')}
      </div>
      <p class="opt-note">${tail}</p>`;
    btn.textContent = '重新验证';
  } catch (e) {
    $('verifyOut').innerHTML = `<p class="opt-note">验证失败：${esc(e.message)}</p>`;
    btn.textContent = '跑最优性验证';
  } finally {
    btn.disabled = false;
  }
};

/* ── 复制 ── */
$('copyBtn').onclick = async () => {
  const d = state.data;
  if (!d) return;
  const g = d.groups.find(x => x.id === state.group) || d.groups[0];
  const lines = [`${d.request.city} ${d.request.date} ${d.request.weekday} · ${d.request.people} 人 · ${d.weather.condition}`,
  ...g.timeline.filter(x => x.type === 'spot' || x.type === 'meal')
    .map(x => `${x.start}-${x.end}  ${x.name}${x.type === 'meal' ? '（午餐）' : ''}`),
    `预算合计 ${yuan(d.budget.total)}，人均 ${yuan(d.budget.perPerson)}`];
  try { await navigator.clipboard.writeText(lines.join('\n')); $('copyBtn').textContent = '已复制'; setTimeout(() => $('copyBtn').textContent = '复制行程', 1600); }
  catch { $('copyBtn').textContent = '复制失败'; }
};

$('howBtn').onclick = () => $('howDialog').showModal();
$('closeHow').onclick = $('okHow').onclick = () => $('howDialog').close();

/* 首屏自动跑一次，打开就能看到效果；带 ?verify=1 时顺带把最优性验证也跑出来 */
window.addEventListener('load', () => {
  setTimeout(() => run({ scroll: false }), 300);
  if (/[?&]verify=1/.test(location.search)) setTimeout(() => $('verifyBtn').click(), 1600);
});
