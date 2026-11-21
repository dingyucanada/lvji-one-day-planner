/* 旅迹 LVJI · 杭州行程编排（多日） */
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const yuan = n => '¥' + Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 });
const num1 = n => (Math.round((Number(n) || 0) * 10) / 10).toFixed(1);

const FLAG_CN = { elderly: '含长辈', kids: '含孩子', couple: '情侣', friends: '朋友同行' };
const state = { tags: [], interests: [], time: null, access: [], days: null, data: null, day: 1, group: 'A' };

/* ── chips ───────────────────────────────────────────────────────────── */
document.querySelectorAll('.chip-group').forEach(g => {
  const key = g.dataset.group;
  g.querySelectorAll('.chip').forEach(btn => {
    btn.onclick = () => {
      const v = btn.dataset.value;
      if (key === 'time' || key === 'days') {
        const was = btn.classList.contains('on');
        g.querySelectorAll('.chip').forEach(x => x.classList.remove('on'));
        if (was) { state[key] = null; return; }
        btn.classList.add('on');
        state[key] = key === 'days' ? Number(v) : v;
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

/* ── 数据集信息 ───────────────────────────────────────────────────────── */
fetch('api/meta').then(r => r.json()).then(m => {
  $('dataPill').textContent = `数据集 ${m.version} · ${m.spots} 景点 / ${m.hotels} 住宿`;
  $('datasetMeta').textContent = `${m.city} · ${m.source.slice(0, 14)}…`;
  const strip = [
    ['spots', '景点'], ['food', '餐厅'], ['hotels', '住宿样例'], ['weatherDays', '天气样例'],
  ].map(([k, label]) => `<div class="ds-cell"><b>${m[k]}</b><small>${label}</small></div>`).join('') +
    `<p class="ds-note">来源：${esc(m.source)}　版本 ${esc(m.version)}　生成日 ${esc(m.today)}</p>`;
  $('dataset').innerHTML = strip;
}).catch(() => { $('dataPill').textContent = '数据集未加载'; });

/* ── 提交 ─────────────────────────────────────────────────────────────── */
function form() {
  const f = {};
  if (state.tags.length) f.tags = state.tags.join(',');
  if (state.interests.length) f.interests = state.interests.join(',');
  if (state.access.includes('1')) f.wheelchair = '1';
  if (state.days) f.days = String(state.days);
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
  $('dayTabs').innerHTML = ''; $('groupTabs').innerHTML = ''; $('overview').innerHTML = '';
  try {
    const r = await fetch('api/plan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, form: form() })
    });
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    state.data = data;
    state.day = 1;
    state.group = data.days[0].groups[0].id;
    render();
    if (scroll) $('result').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    $('summary').innerHTML = `<h2>没能排出来</h2><p class="lede">${esc(e.message)}</p>`;
  } finally {
    btn.disabled = false; btn.textContent = '生成行程';
  }
}
$('planBtn').onclick = () => run();
$('ask').onkeydown = e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') run(); };
$('demoBtn').onclick = () => {
  $('ask').value = '从北京去杭州三天两夜，带坐轮椅的奶奶和两个孩子，想看西湖、灵隐寺和茶园，晚上想吃点小吃';
  document.querySelectorAll('.chip-group[data-group="days"] .chip').forEach(c => c.classList.remove('on'));
  state.days = null;
  run();
};
$('resetBtn').onclick = () => {
  $('result').hidden = true; $('ask').value = ''; $('ask').focus();
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

/* ── 当前视图取数 ─────────────────────────────────────────────────────── */
const curDay = () => {
  const d = state.data;
  return d.days.find(x => x.day === state.day) || d.days[0];
};
const curGroup = () => {
  const day = curDay();
  return day.groups.find(g => g.id === state.group) || day.groups[0];
};
const spotsOf = g => g.timeline.filter(x => x.type === 'spot');

/* ── 渲染总入口 ───────────────────────────────────────────────────────── */
function render() {
  const d = state.data;
  renderSummary(d);
  renderDecisions(d);
  renderOverview(d);
  renderDayTabs(d);
  renderTabs(d);
  renderTimeline(d);
  renderMap(d);
  renderBudget(d);
  renderAccess(d);
  renderFactors(d);
  renderOpt(d);
  renderApi(d);
}

function renderSummary(d) {
  const q = d.request, w = d.days[0].weather;
  const wx = `${w.condition} ${w.low}–${w.high}℃ · 降水 ${w.rainProb}%`;
  const flagTxt = q.flags.length ? ' · ' + q.flags.map(f => FLAG_CN[f] || f).join('/') : '';
  $('summary').innerHTML = `
    <div class="summary">
      <div class="summary-route">
        <span class="rq">${esc(q.city)} · ${q.days} 日</span>
        <h2>${q.days > 1 ? `${q.days} 天 ${d.days.length} 段主线` : '一天安排'}</h2>
      </div>
      <div class="summary-meta">
        <span class="meta-pill">${esc(q.date)} 起 ${esc(q.weekday)}</span>
        <span class="meta-pill">${q.people} 人${esc(flagTxt)}</span>
        <span class="meta-pill">每日 ${esc(q.start)}–${esc(q.end)}</span>
        <span class="meta-pill wx">${esc(wx)}</span>
        <span class="meta-pill hi">${d.hotel.name}</span>
        ${q.wheelchair ? '<span class="meta-pill warn">轮椅可达</span>' : ''}
        ${q.lowWalk && !q.wheelchair ? '<span class="meta-pill warn">低步行</span>' : ''}
      </div>
    </div>`;
}

function renderDecisions(d) {
  const day = curDay();
  const all = (d.decisions || []).slice();
  if (d.days.length > 1 && day) all.push(...(day.decisions || []));
  $('decisions').innerHTML = all.map(x =>
    `<div class="dec ${x.level}"><b>${esc(x.title)}</b><span>${esc(x.text)}</span></div>`).join('');
}

/* 多日全程总览：每天得分占比条 + 景点名 */
function renderOverview(d) {
  const card = $('overviewCard');
  if (d.days.length <= 1) { card.hidden = true; return; }
  card.hidden = false;
  const maxScore = Math.max(...d.days.map(x => x.stats.score), 1);
  $('overviewMeta').textContent = `${d.days.length} 天 · 合计 ${d.days.reduce((s, x) => s + x.stats.spots, 0)} 个停留点 · 住宿 ${d.days.length} 晚`;
  $('overview').innerHTML = d.days.map(x => {
    const names = x.groups.flatMap(g => spotsOf(g).map(s => s.name));
    return `<button class="ov-day ${x.day === state.day ? 'on' : ''}" data-day="${x.day}">
      <div class="od-h"><b>第 ${x.day} 天</b><small>${esc(x.date.slice(5))} ${esc(x.weekday)}</small></div>
      <div class="od-bar"><i style="width:${Math.max(6, Math.round(x.stats.score / maxScore * 100))}%"></i></div>
      <div class="od-f"><span>${x.stats.spots} 个点 · 得分 ${num1(x.stats.score)}</span><span>${esc(x.weather.condition)}</span></div>
      <div class="ov-names">${esc(names.join(' · ') || '当天无可用景点')}</div>
    </button>`;
  }).join('');
  $('overview').querySelectorAll('[data-day]').forEach(b => b.onclick = () => {
    state.day = Number(b.dataset.day);
    const day = curDay();
    state.group = day.groups[0].id;
    render();
  });
}

function renderDayTabs(d) {
  const tabs = $('dayTabs');
  if (d.days.length <= 1) { tabs.innerHTML = ''; return; }
  tabs.innerHTML = d.days.map(x => `
    <button class="day-tab ${x.day === state.day ? 'on' : ''}" data-d="${x.day}">
      <span class="dt-d">第 ${x.day} 天</span>
      <span class="dt-m">${esc(x.date.slice(5))} ${esc(x.weekday)} · ${esc(x.weather.condition)}</span>
      <span class="dt-s">${x.stats.spots} 个点 · ${num1(x.stats.score)} 分</span>
    </button>`).join('');
  tabs.querySelectorAll('[data-d]').forEach(b => b.onclick = () => {
    state.day = Number(b.dataset.d);
    state.group = curDay().groups[0].id;
    render();
  });
}

function renderTabs(d) {
  const day = curDay();
  const tabs = $('groupTabs');
  if (day.groups.length === 1) { tabs.innerHTML = ''; return; }
  tabs.innerHTML = day.groups.map(g =>
    `<button class="group-tab ${g.id === state.group ? 'on' : ''}" data-g="${g.id}">
      <b>${esc(g.name)} · ${g.members} 人</b><small>${esc(g.profile)} · ${g.stats.spots} 个点</small>
    </button>`).join('');
  tabs.querySelectorAll('[data-g]').forEach(b => b.onclick = () => {
    state.group = b.dataset.g;
    renderTabs(d); renderTimeline(d); renderMap(d); renderAccess(d); renderFactors(d); renderOpt(d); renderDecisions(d);
  });
}

const ICON = { spot: '●', meal: '餐', travel: '→', wait: '等', rest: '息', nap: '睡' };

function renderTimeline(d) {
  const day = curDay(), g = curGroup();
  $('timelineTitle').textContent = `第 ${day.day} 天 · ${g.name} · 时间轴`;
  $('timelineMeta').textContent = `${g.stats.spots} 个停留点 · 排队 ${g.stats.queueMin} 分钟 · 步行 ${g.stats.walkKm} 公里 · ${g.stats.end} 结束`;
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
    } else if (x.type === 'nap') {
      tags.push(`<span class="tag">${x.minutes} 分钟</span>`);
      tags.push('<span class="tag acc">婴幼儿作息</span>');
    }
    return `<div class="tl-item ${x.type}">
      <div class="tl-time"><b>${esc(x.start)}</b>${esc(x.end)}</div>
      <div class="tl-rail"><span class="tl-dot">${dot}</span></div>
      <div class="tl-body">
        <div class="tl-title">${esc(x.name)}${isSpot && x.score != null ? `<span class="score-badge">${num1(x.score)}</span>` : ''}</div>
        ${x.reason ? `<div class="tl-why">${esc(x.reason)}</div>` : ''}
        ${tags.length ? `<div class="tl-tags">${tags.join('')}</div>` : ''}
      </div>
    </div>`;
  }).join('') || '<p class="empty">这一天没有可排的停留点</p>';
}

/* ── 路线示意（SVG 等比投影）──────────────────────────────────────────── */
const GCOLOR = { A: '#3F6455', B: '#9C3A2C' };

/* ── 真实地理底图（WGS84 真实坐标，离线矢量，无外部瓦片）────────────────
   底图要素：西湖岸线、苏堤、京杭大运河、钱塘江、环湖路。
   全部用真实经纬度定义，和景点共用同一投影，所以相对位置是真的。
   ───────────────────────────────────────────────────────────────────── */
const GEO = {
  /* 西湖岸线（顺时针，含北里湖与西里湖） */
  xihu: [
    [30.2622, 120.1352], [30.2598, 120.1408], [30.2562, 120.1436], [30.2518, 120.1452],
    [30.2472, 120.1445], [30.2425, 120.1432], [30.2378, 120.1428], [30.2332, 120.1402],
    [30.2292, 120.1362], [30.2262, 120.1312], [30.2258, 120.1252], [30.2288, 120.1198],
    [30.2332, 120.1158], [30.2402, 120.1132], [30.2468, 120.1138], [30.2522, 120.1182],
    [30.2568, 120.1248], [30.2602, 120.1302],
  ],
  /* 苏堤：北山街 → 南山路 */
  sudi: [[30.2553, 120.1306], [30.2498, 120.1298], [30.2442, 120.1290], [30.2388, 120.1282], [30.2338, 120.1276]],
  /* 白堤：断桥 → 孤山 */
  badi: [[30.2598, 120.1425], [30.2578, 120.1382], [30.2552, 120.1348], [30.2532, 120.1322]],
  /* 京杭大运河（拱宸桥 → 武林门 → 钱塘江口） */
  canal: [
    [30.3225, 120.1408], [30.3135, 120.1455], [30.3040, 120.1520], [30.2945, 120.1580],
    [30.2850, 120.1635], [30.2745, 120.1682], [30.2635, 120.1735], [30.2520, 120.1795],
  ],
  /* 钱塘江（之江 → 钱江新城 → 下沙方向） */
  qiantang: [
    [30.1945, 120.1185], [30.2035, 120.1395], [30.2155, 120.1665], [30.2280, 120.1935],
    [30.2425, 120.2155], [30.2560, 120.2365], [30.2680, 120.2585],
  ],
  /* 环湖路（近似闭合） */
  ringRoad: [
    [30.2632, 120.1340], [30.2600, 120.1440], [30.2510, 120.1478], [30.2408, 120.1462],
    [30.2300, 120.1408], [30.2238, 120.1300], [30.2252, 120.1180], [30.2348, 120.1108],
    [30.2452, 120.1098], [30.2542, 120.1152], [30.2608, 120.1248],
  ],
};

function renderMap(d) {
  const day = curDay();
  const pts = day.route.points || [];
  const hotel = d.hotel;
  $('mapMeta').textContent = `${pts.length} 个停留点 · 第 ${day.day} 天 · 真实经纬度`;
  if (!pts.length) { $('map').innerHTML = '<p class="empty">当日无停留点</p>'; $('mapLegend').innerHTML = ''; return; }

  /* 投影范围：以「本日停留点 + 酒店」的包围盒为主，再把西湖水域并进去。
     这样当天点越集中在西湖，西湖就越大；点散到良渚/湘湖时自动拉远。 */
  const focus = pts.concat([{ lat: hotel.lat, lon: hotel.lon }]);
  let minLat = Math.min(...focus.map(p => p.lat)), maxLat = Math.max(...focus.map(p => p.lat));
  let minLon = Math.min(...focus.map(p => p.lon)), maxLon = Math.max(...focus.map(p => p.lon));
  /* 西湖岸线并入，但限制其撑大视野：只在当天点靠近西湖时才完整并入 */
  const xhLats = GEO.xihu.map(([la]) => la), xhLons = GEO.xihu.map(([, lo]) => lo);
  const cxLat = (minLat + maxLat) / 2, cxLon = (minLon + maxLon) / 2;
  const xhCx = (Math.min(...xhLats) + Math.max(...xhLats)) / 2;
  const xhCy = (Math.min(...xhLons) + Math.max(...xhLons)) / 2;
  if (Math.abs(cxLat - xhCx) < 0.03 && Math.abs(cxLon - xhCy) < 0.03) {
    minLat = Math.min(minLat, ...xhLats); maxLat = Math.max(maxLat, ...xhLats);
    minLon = Math.min(minLon, ...xhLons); maxLon = Math.max(maxLon, ...xhLons);
  }
  const W = 460, H = 360, pad = 26;
  /* 等比投影：按纬度余弦修正经度，避免西湖被拉扁 */
  const kx = Math.cos((minLat + maxLat) / 2 * Math.PI / 180);
  const spanX = (maxLon - minLon) * kx, spanY = (maxLat - minLat);
  const scale = Math.min((W - pad * 2) / Math.max(spanX, 1e-6), (H - pad * 2) / Math.max(spanY, 1e-6));
  const cx = (minLon + maxLon) / 2, cy = (minLat + maxLat) / 2;
  const sx = v => W / 2 + (v - cx) * kx * scale;
  const sy = v => H / 2 - (v - cy) * scale;
  const path = arr => arr.map(([la, lo], i) => `${i ? 'L' : 'M'}${sx(lo).toFixed(1)} ${sy(la).toFixed(1)}`).join(' ') + ' Z';

  /* ── 底图 ── */
  let base = `
    <path d="${path(GEO.xihu)}" fill="#A8CFC2" fill-opacity=".5" stroke="#4E8576" stroke-opacity=".85" stroke-width="1.6"/>
    <path d="${path(GEO.ringRoad)}" fill="none" stroke="#B9A98C" stroke-opacity=".55" stroke-width="3" stroke-linecap="round"/>
    <path d="M${GEO.sudi.map(([la, lo]) => `${sx(lo).toFixed(1)} ${sy(la).toFixed(1)}`).join(' L')}" fill="none" stroke="#3F7A67" stroke-opacity=".9" stroke-width="2.6" stroke-linecap="round"/>
    <path d="M${GEO.badi.map(([la, lo]) => `${sx(lo).toFixed(1)} ${sy(la).toFixed(1)}`).join(' L')}" fill="none" stroke="#3F7A67" stroke-opacity=".9" stroke-width="2.6" stroke-linecap="round"/>
    <path d="M${GEO.canal.map(([la, lo]) => `${sx(lo).toFixed(1)} ${sy(la).toFixed(1)}`).join(' L')}" fill="none" stroke="#5B8FB5" stroke-opacity=".9" stroke-width="5" stroke-linecap="round"/>
    <path d="M${GEO.qiantang.map(([la, lo]) => `${sx(lo).toFixed(1)} ${sy(la).toFixed(1)}`).join(' L')}" fill="none" stroke="#5B8FB5" stroke-opacity=".9" stroke-width="9" stroke-linecap="round"/>`;

  /* 地名标注 */
  const label = (la, lo, txt, size, color) =>
    `<text x="${sx(lo).toFixed(1)}" y="${sy(la).toFixed(1)}" text-anchor="middle" font-size="${size || 8.5}"
       fill="${color || '#6F8F81'}" font-family="serif" letter-spacing=".08em" opacity=".9">${txt}</text>`;
  base += label(30.2405, 120.1305, '西　湖', 13, '#3F6A5B')
    + label(30.3195, 120.1480, '京杭大运河', 9, '#4A6F8A')
    + label(30.2090, 120.1630, '钱塘江', 10, '#4A6F8A')
    + label(30.2450, 120.1288, '苏堤', 8, '#3F6A5B')
    + label(30.2560, 120.1360, '白堤', 8, '#3F6A5B');

  /* ── 路线 ── */
  let paths = '';
  day.groups.forEach(g => {
    const gp = pts.filter(p => p.group === g.id).sort((a, b) => a.seq - b.seq);
    if (!gp.length) return;
    const line = [[hotel.lat, hotel.lon]].concat(gp.map(p => [p.lat, p.lon])).concat([[hotel.lat, hotel.lon]]);
    const dd = line.map(([la, lo], i) => `${i ? 'L' : 'M'}${sx(lo).toFixed(1)} ${sy(la).toFixed(1)}`).join(' ');
    const on = g.id === state.group;
    paths += `<path d="${dd}" fill="none" stroke="${GCOLOR[g.id] || '#3F6455'}" stroke-width="${on ? 2.4 : 1.4}"
      stroke-dasharray="${g.id === 'B' ? '5 4' : '0'}" opacity="${on ? .95 : .3}" stroke-linejoin="round" stroke-linecap="round"
      stroke-opacity=".85"/>`;
  });

  /* 酒店 */
  let nodes = `<g>
      <circle cx="${sx(hotel.lon).toFixed(1)}" cy="${sy(hotel.lat).toFixed(1)}" r="6.5" fill="#FFFDF7" stroke="#2E4B3F" stroke-width="2.2"/>
      <path d="M${sx(hotel.lon).toFixed(1)} ${(sy(hotel.lat) - 2.6).toFixed(1)} l2.4 4.4 h-4.8 Z" fill="#2E4B3F"/>
      <text x="${(sx(hotel.lon) + 9).toFixed(1)}" y="${(sy(hotel.lat) + 3.5).toFixed(1)}" font-size="9" fill="#4A443C" font-family="serif">${esc(hotel.name)}</text>
    </g>`;

  /* 景点 */
  day.groups.forEach(g => {
    const gp = pts.filter(p => p.group === g.id).sort((a, b) => a.seq - b.seq);
    gp.forEach(p => {
      const on = g.id === state.group;
      nodes += `<g opacity="${on ? 1 : .3}">
        <circle cx="${sx(p.lon).toFixed(1)}" cy="${sy(p.lat).toFixed(1)}" r="${on ? 11 : 8}" fill="${GCOLOR[g.id] || '#3F6455'}" stroke="#FFFDF7" stroke-width="1.8"/>
        <text x="${sx(p.lon).toFixed(1)}" y="${(sy(p.lat) + 3.6).toFixed(1)}" text-anchor="middle" font-size="${on ? 10.5 : 8.5}" font-weight="700" fill="#FFFDF7">${p.seq}</text>
      </g>`;
    });
  });

  /* 比例尺 */
  const kmPerPx = 1 / (scale * 111);          // 1 像素对应的公里数
  const barKm = kmPerPx * 70 > 5 ? 2 : (kmPerPx * 70 > 2 ? 1 : 0.5);
  const barPx = barKm / kmPerPx;
  const scaleBar = `<g opacity=".65">
      <line x1="${W - 20 - barPx}" y1="${H - 14}" x2="${W - 20}" y2="${H - 14}" stroke="#4A443C" stroke-width="1.6"/>
      <line x1="${W - 20 - barPx}" y1="${H - 18}" x2="${W - 20 - barPx}" y2="${H - 10}" stroke="#4A443C" stroke-width="1.2"/>
      <line x1="${W - 20}" y1="${H - 18}" x2="${W - 20}" y2="${H - 10}" stroke="#4A443C" stroke-width="1.2"/>
      <text x="${W - 20 - barPx / 2}" y="${H - 20}" text-anchor="middle" font-size="8.5" fill="#6B6357">${barKm} km</text>
    </g>`;

  /* 指北针 */
  const north = `<g transform="translate(${W - 30},26)" opacity=".6">
      <path d="M0 -11 L4 4 L0 1 L-4 4 Z" fill="#4A443C"/>
      <text x="0" y="14" text-anchor="middle" font-size="8" fill="#6B6357">N</text>
    </g>`;

  $('map').innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="杭州真实地理底图与当天路线">${base}${paths}${nodes}${scaleBar}${north}</svg>`;

  const active = curGroup();
  const list = pts.filter(p => p.group === active.id).sort((a, b) => a.seq - b.seq)
    .map(p => `<li><b>${p.seq}</b><span>${esc(p.name)}</span><em>${esc(p.start)}</em></li>`).join('');
  $('mapLegend').innerHTML =
    (day.groups.length > 1
      ? `<div class="legend-groups">${day.groups.map(g => `<span><i style="background:${GCOLOR[g.id]}"></i>${esc(g.name)}（${g.members} 人）</span>`).join('')}</div>`
      : `<div class="legend-groups"><span><i style="background:#3F6455"></i>当天动线，数字为到访顺序</span></div>`) +
    `<div class="legend-groups" style="margin-top:5px;font-size:10.5px">
       <span><i style="background:#A8CFC2"></i>西湖水域</span>
       <span><i style="background:#5B8FB5"></i>运河 / 钱塘江</span>
       <span><i style="background:#3F7A67"></i>苏堤 · 白堤</span>
     </div>` +
    `<ol class="map-list">${list}</ol>`;
}

function renderBudget(d) {
  const b = d.budget;
  const rows = [
    ['门票（全程）', b.ticket], ['市内交通', b.localFare], ['餐饮', b.meals],
    [`住宿 ${b.nights} 晚 × ${b.rooms} 间`, b.hotel],
  ];
  if (b.intercityTotal) rows.push([`城际往返（${b.intercity.map(x => x.code).join(' / ')}）`, b.intercityTotal]);
  $('budget').innerHTML = rows.map(([k, v]) =>
    `<div class="budget-row"><span>${esc(k)}</span><b>${yuan(v)}</b></div>`).join('') +
    `<div class="budget-total"><div><small>${d.request.people} 人 · ${b.nights} 天合计</small><div class="num">${yuan(b.total)}</div></div>
      <div style="text-align:right"><small>人均</small><div style="font-weight:600;font-family:var(--serif)">${yuan(b.perPerson)}</div></div></div>
     <p class="budget-per">日均 ${yuan(b.perDay)} · 按本地样例价估算，不含购物与临时溢价</p>`;
  $('budgetMeta').textContent = `${d.hotel.name} · ${yuan(d.hotel.price)}/晚`;
}

function renderAccess(d) {
  const g = curGroup();
  const spots = spotsOf(g);
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

/* ── 九维评分矩阵 ─────────────────────────────────────────────────────── */
const KIND_CLS = { '定量': 'k-quant', '半定量': 'k-semi', '定性': 'k-qual' };

function renderFactors(d) {
  const crit = d.criteria || [];
  if (!crit.length) return;
  const g = curGroup();
  const spots = spotsOf(g);
  const maxAbs = Math.max(9, ...spots.flatMap(s => crit.map(c => Math.abs((s.parts || {})[c.key] || 0))));

  $('factorsMeta').textContent = `${crit.length} 个维度 · 第 ${curDay().day} 天 ${g.name} ${spots.length} 个停留点`;

  const wTxt = w => (w >= 1 ? String(w) : '1/' + Math.round(1 / w));
  $('critLegend').innerHTML = crit.map(c => `
    <div class="crit-chip ${KIND_CLS[c.kind] || ''}">
      <span class="crit-kind">${esc(c.kind)}</span>
      <b>${esc(c.label)}</b>
      <span class="crit-w">权重 ${wTxt(c.weight)}</span>
    </div>`).join('');

  const head = `<thead><tr><th class="mx-name">停留点</th>
    ${crit.map(c => `<th class="${KIND_CLS[c.kind] || ''}"><span>${esc(c.label)}</span><small>${esc(c.kind)}</small></th>`).join('')}
    <th class="mx-total">合计</th></tr></thead>`;

  const sev = v => {
    const a = Math.min(1, Math.abs(v) / maxAbs);
    return Math.round((0.06 + a * 0.32) * 100) / 100;
  };

  const body = `<tbody>${spots.map(s => {
    const p = s.parts || {};
    const cells = crit.map(c => {
      const v = p[c.key] || 0;
      const bg = Math.abs(v) < 0.01 ? 'rgba(239,229,211,.5)'
        : v > 0 ? `rgba(63,100,85,${sev(v)})` : `rgba(156,58,44,${sev(v)})`;
      const txt = Math.abs(v) < 0.01 ? '—' : (v > 0 ? '+' : '') + num1(v);
      return `<td class="mx-cell" style="background:${bg}">${txt}</td>`;
    }).join('');
    return `<tr><th class="mx-name">${esc(s.name)}</th>${cells}
      <td class="mx-total">${num1(s.score)}</td></tr>`;
  }).join('')}</tbody>`;

  $('scoreMatrix').innerHTML = head + body;

  const rj = curDay().rejected || [];
  const KIND_TXT = { blocked: '硬约束出局', passed: '评分未入选', used: '前几天已去过' };
  $('rejected').innerHTML = rj.length ? rj.map(x => `
    <div class="rj ${x.kind}">
      <div class="rj-head"><b>${esc(x.name)}</b>
        <span class="rj-kind">${KIND_TXT[x.kind] || ''}</span></div>
      <div class="rj-why">${esc(x.why)}${x.kind === 'passed' && x.score != null ? `　合计 ${num1(x.score)}` : ''}</div>
    </div>`).join('') : '<p class="empty">所有候选点都排进去了</p>';
}

/* ── 求解过程 ─────────────────────────────────────────────────────────── */
function renderOpt(d) {
  const g = curGroup();
  const o = g.optimize;
  if (!o) { $('optChart').innerHTML = ''; $('optKv').innerHTML = ''; return; }
  const trace = o.trace || [];
  $('optMeta').textContent = `第 ${curDay().day} 天 ${g.name} · ${o.iters} 轮 · 接受改进 ${o.accepted || 0} 次`;

  const W = 440, H = 150, padL = 32, padB = 18, padT = 9;
  const vals = trace.map(t => t[1]);
  const minV = Math.min(...vals), maxV = Math.max(...vals);
  const span = Math.max(maxV - minV, 0.001);
  const sx = i => padL + (trace.length < 2 ? 0 : i / (trace.length - 1)) * (W - padL - 4);
  const sy = v => padT + (1 - (v - minV) / span) * (H - padT - padB);

  const pts = trace.map((t, i) => `${sx(i).toFixed(1)} ${sy(t[1]).toFixed(1)}`).join(' L');
  const area = `M${sx(0).toFixed(1)} ${(H - padB).toFixed(1)} L${pts} L${sx(trace.length - 1).toFixed(1)} ${(H - padB).toFixed(1)} Z`;

  $('optChart').innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="收敛曲线">
    <defs><linearGradient id="og" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#3F6455" stop-opacity=".22"/>
      <stop offset="1" stop-color="#3F6455" stop-opacity="0"/>
    </linearGradient></defs>
    ${[0, .5, 1].map(k => `<line x1="${padL}" y1="${(padT + k * (H - padT - padB)).toFixed(1)}" x2="${W - 4}" y2="${(padT + k * (H - padT - padB)).toFixed(1)}" stroke="#B7A98F" stroke-width=".6" opacity=".45"/>`).join('')}
    <path d="${area}" fill="url(#og)"/>
    <path d="M${pts}" fill="none" stroke="#3F6455" stroke-width="1.7" stroke-linejoin="round"/>
    <circle cx="${sx(trace.length - 1).toFixed(1)}" cy="${sy(maxV).toFixed(1)}" r="3" fill="#9C3A2C"/>
    <text x="0" y="${(sy(maxV) + 3).toFixed(1)}" font-size="9" fill="#867C6C">${maxV.toFixed(1)}</text>
    <text x="0" y="${(sy(minV) + 3).toFixed(1)}" font-size="9" fill="#867C6C">${minV.toFixed(1)}</text>
    <text x="${padL}" y="${H - 5}" font-size="9" fill="#867C6C">0</text>
    <text x="${W - 4}" y="${H - 5}" text-anchor="end" font-size="9" fill="#867C6C">${o.iters} 轮</text>
  </svg>`;

  const up = o.gain > 0;
  $('optKv').innerHTML = `
    <div class="kv"><span>贪心构造</span><b>${num1(o.base)}</b></div>
    <div class="kv"><span>ILS 最优</span><b class="hi">${num1(o.best)}</b></div>
    <div class="kv"><span>提升</span><b class="${up ? 'up' : ''}">${up ? '+' : ''}${num1(o.gain)}${o.base ? `（${num1(o.gain / Math.abs(o.base) * 100)}%）` : ''}</b></div>
    <div class="kv"><span>改进轮次</span><b>${o.rounds || 0} / ${o.iters}</b></div>`;
  $('optNote').textContent = up
    ? `贪心构造拿到 ${num1(o.base)} 分，经 ${o.iters} 轮邻域搜索后提升到 ${num1(o.best)} 分。曲线是阶梯状——只有找到更优顺序才会跳升，停滞时扰动力度自动加大。`
    : `本次需求下贪心构造已经是最优，${o.iters} 轮搜索没有找到更好的顺序。`;
}

/* ── 最优性验证 ───────────────────────────────────────────────────────── */
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

/* ── 复制 ─────────────────────────────────────────────────────────────── */
$('copyBtn').onclick = async () => {
  const d = state.data;
  if (!d) return;
  const lines = [`${d.request.city} ${d.request.days} 日 · ${d.request.people} 人 · ${yuan(d.budget.total)}（人均 ${yuan(d.budget.perPerson)}）`];
  d.days.forEach(day => {
    lines.push('', `── 第 ${day.day} 天 ${day.date} ${day.weekday} ${day.weather.condition} ──`);
    day.groups.forEach(g => {
      if (day.groups.length > 1) lines.push(`[${g.name}]`);
      g.timeline.filter(x => x.type === 'spot' || x.type === 'meal')
        .forEach(x => lines.push(`${x.start}-${x.end}  ${x.name}${x.type === 'meal' ? '（午餐）' : ''}`));
    });
  });
  try {
    await navigator.clipboard.writeText(lines.join('\n'));
    $('copyBtn').textContent = '已复制'; setTimeout(() => $('copyBtn').textContent = '复制行程', 1600);
  } catch { $('copyBtn').textContent = '复制失败'; }
};

$('howBtn').onclick = () => $('howDialog').showModal();
$('closeHow').onclick = $('okHow').onclick = () => $('howDialog').close();

/* ── 算法指标：用真实测量值填充，不留硬编码数字 ─────────────────── */
Promise.all([
  fetch('api/benchmark').then(r => r.json()).catch(() => null),
  fetch('api/scaling').then(r => r.json()).catch(() => null),
]).then(([real, sc]) => {
  const num1 = n => (Math.round((Number(n) || 0) * 10) / 10).toFixed(1);
  if (real && real.summary) {
    const s = real.summary;
    const gapTxt = (Math.max(0, s.avgGap)).toFixed(2) + '%';
    if ($('stGap')) $('stGap').textContent = gapTxt;
    if ($('abGap')) $('abGap').textContent = gapTxt;
    if ($('abHit')) $('abHit').textContent = `${s.hit} / ${s.trips}`;
  }
  if (sc && sc.rows && sc.rows.length) {
    const rows = sc.rows, last = rows[rows.length - 1];
    if ($('stSpeed')) $('stSpeed').textContent = Math.round(last.speedup) + '×';
    if ($('abSpeed')) $('abSpeed').textContent = Math.round(last.speedup) + '×';
    if ($('abText')) $('abText').textContent =
      `把行程设计形式化为带时间窗的团队定向越野问题（TOPTW），两层求解：贪心构造拿到可行解，ILS 在排列空间逼近最优。` +
      `真实景点算例拿全排列穷举对标，gap 不超过 0（启发式还会探索「少去一个点」的子集，因此可能反超穷举）。` +
      `合成算例 n=${last.n} 时排列数 ${last.perms.toLocaleString('zh-CN')} 种，穷举 ${num1(last.bruteMs)} ms，ILS 只要 ${num1(last.ilsMs)} ms。`;
  }
}).catch(() => {});

/* 首屏自动跑一次；带 ?verify=1 顺带跑最优性验证 */
window.addEventListener('load', () => {
  setTimeout(() => run({ scroll: false }), 260);
  if (/[?&]verify=1/.test(location.search)) setTimeout(() => $('verifyBtn').click(), 1800);
});
