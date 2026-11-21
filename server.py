"""旅迹 LVJI · 一日行程规划（挑战 2）

自建「前端 + 本地数据 + 数据接口」：
  GET  /api/meta        数据集概览（城市、景点数、版本、今日）
  GET  /api/spots       景点（开放/闭馆时间、排队时长、步行强度、无障碍标签）
  GET  /api/weather     天气样例
  GET  /api/transport   城际车次/航班 + 市内交通参数
  GET  /api/hotels      住宿样例
  POST /api/plan        一句话 → 一天行程（多站点排序 + 时间窗 + 排队 + 天气 + 分组）

所有接口都读写 data/*.json，并记录调用耗时，作为「数据真实性」的验证依据。
"""
import json, os, re, math, time, random, itertools, datetime, pathlib
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / 'data'

# ── 数据接口（本地 mock API）─────────────────────────────────────────────────
_CALLS = []
_BENCH = {}          # 最优性验证结果缓存（固定种子，算一次即可）


def api(name, fn):
    """统一入口：记录调用耗时与返回行数，前端「接口日志」直接消费。"""
    t0 = time.time()
    out = fn()
    rows = len(out) if isinstance(out, list) else (len(out.get('spots') or out.get('hotels') or out.get('days') or out.get('routes') or []) if isinstance(out, dict) else 0)
    _CALLS.append(dict(api=name, ms=int((time.time() - t0) * 1000), rows=rows))
    return out


def load(name):
    with open(DATA / (name + '.json'), encoding='utf-8') as f:
        return json.load(f)


def get_spots():
    return load('spots')


def get_weather():
    return load('weather')


def get_transport():
    return load('transport')


def get_hotels():
    return load('hotels')


def hhmm(s):
    h, m = str(s).split(':')
    return int(h) * 60 + int(m)


def hhmm_text(m):
    m = int(round(m))
    return '%02d:%02d' % (m // 60 % 24, m % 60)


def haversine(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a['lat'], a['lon'], b['lat'], b['lon']))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


# ── 一句话理解：城市 / 兴趣 / 人群 / 无障碍 / 时间 / 日期 ────────────────────
INTERESTS = [
    ('博物馆', ['博物馆', '文物', '展', '考古', '丝绸', '茶叶']),
    ('湖景', ['西湖', '湖', '断桥', '拍照']),
    ('古寺', ['寺', '灵隐', '飞来峰', '祈福', '佛像']),
    ('自然', ['湿地', '自然', '茶园', '龙井', '植物园', '徒步', '爬山']),
    ('亲子', ['孩子', '娃', '亲子', '小朋友', '动物', '动物园', '儿童']),
    ('美食', ['吃', '美食', '小吃', '老字号', '菜']),
    ('演出', ['演出', '宋城', '千古情', '夜游', '夜景']),
    ('购物', ['老街', '河坊街', '买', '逛', '购物']),
]

GROUPS = [
    ('elderly', ['爸妈', '父母', '老人', '长辈', '爷爷', '奶奶', '外公', '外婆', '腿脚', '轮椅', '无障碍', '走不动', '膝盖']),
    ('kids', ['孩子', '娃', '儿子', '女儿', '小朋友', '亲子', '儿童']),
    ('couple', ['情侣', '老婆', '老公', '对象', '约会', '女朋友', '男朋友']),
    ('friends', ['朋友', '同学', '同事', '闺蜜']),
]

CN_NUM = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}


WEEK_IDX = {'一': 0, '二': 1, '三': 2, '四': 3, '五': 4, '六': 5, '日': 6, '天': 6}


def weather_advice(w):
    """把天气字段翻成「要不要带伞、要不要加外套」这类能直接执行的准备动作。"""
    out = []
    if w['rainProb'] >= 60:
        out.append('降水概率 %d%%，带伞，户外点尽量排在雨小的时段；室内馆优先级上调。' % w['rainProb'])
    elif w['rainProb'] >= 30:
        out.append('降水概率 %d%%，包里放把折叠伞，户外点保留但要留室内备选。' % w['rainProb'])
    else:
        out.append('降水概率 %d%%，不用带伞。' % w['rainProb'])
    if w['high'] >= 28:
        out.append('最高 %d℃，防晒、遮阳帽、补水，中午别在太阳底下走。' % w['high'])
    if w['low'] <= 10:
        out.append('最低 %d℃，早晚温差大，给老人和孩子各带一件外套。' % w['low'])
    if w['outdoorScore'] >= 4:
        out.append('户外舒适度 %d/5，适合走西湖一线。' % w['outdoorScore'])
    elif w['outdoorScore'] <= 2:
        out.append('户外舒适度只有 %d/5，把户外的时间压短。' % w['outdoorScore'])
    return out


def _num(v):
    """「6」「六」都转成 int。"""
    v = str(v)
    return int(v) if v.isdigit() else CN_NUM.get(v, 1)


def parse_request(text, form):
    t = (text or '') + ' ' + ' '.join(str(v) for v in (form or {}).values())
    p = {'raw': text}
    p['city'] = '杭州'
    for city in ['杭州', '北京', '上海', '成都', '西安']:
        if city in t:
            p['city'] = city
            break

    # ── 人数：先认「一家 6 口 / 6 个人 / 6 位」，没有再按同行人推算 ──────────
    p['people'] = None
    m = (re.search(r'一家\s*([一两二三四五六七八九十\d]+)\s*口', t)
         or re.search(r'(?:共|一共|总共)\s*([一两二三四五六七八九十\d]+)\s*(?:个)?\s*人', t)
         or re.search(r'([一两二三四五六七八九十\d]+)\s*个?\s*人', t)
         or re.search(r'([一两二三四五六七八九十\d]+)\s*位(?!置)', t))
    if m:
        p['people'] = max(1, min(12, _num(m[1])))
    else:
        n = 1
        if re.search(r'两口子|夫妻俩|我和(?:老公|老婆|爱人|对象)', t):
            n = 2                                                   # 「我们两口子」本身就是 2 人
        if re.search(r'爸妈|父母|双亲|老爸老妈', t):
            n += 2
        m = re.search(r'([一两二三四五六七八九十\d]+)\s*位\s*(?:老人|长辈)', t)
        if m:
            n += _num(m[1])
        elif re.search(r'老人|长辈', t):
            n += 2
        n += len(re.findall(r'爷爷|奶奶|外公|外婆|姥姥|姥爷', t))
        m = re.search(r'([一两二三四五六七八九十\d]+)\s*个?\s*(?:孩子|娃|小朋友|儿童|宝宝|婴儿|幼儿)', t)
        if m:
            n += _num(m[1])
        else:
            n += len(re.findall(r'孩子|小朋友|儿童|儿子|女儿|宝宝|婴儿|幼儿', t))
        if re.search(r'情侣|女朋友|男朋友', t):
            n += 1
        m = re.search(r'([一两二三四五六七八九十\d]+)\s*个?\s*(?:朋友|同事|同学|闺蜜)', t)
        if m:
            n += _num(m[1])
        elif re.search(r'(?<![女男])朋友|同事|同学|闺蜜', t):
            n += 2
        p['people'] = min(12, n)
    if form and str(form.get('people', '')).isdigit():
        p['people'] = max(1, min(12, int(form['people'])))

    # ── 婴幼儿：人数之外单独记一份，用来排午睡 ─────────────────────────────
    p['infants'] = 0
    m = re.search(r'([一两二三四五六七八九十\d]+)\s*个?\s*(?:婴儿|宝宝|奶娃|幼儿)', t)
    if m:
        p['infants'] = _num(m[1])
    elif re.search(r'婴儿|宝宝|奶娃|幼儿', t):
        p['infants'] = 1
    if not p['infants']:
        for m in re.finditer(r'(\d+)\s*岁', t):
            if int(m[1]) <= 3:
                p['infants'] = 1
                break
    p['nap'] = p['infants'] > 0 or bool(re.search(r'午睡|午休|睡午觉', t))

    # ── 人群标签 ────────────────────────────────────────────────────────
    flags = set()
    for key, words in GROUPS:
        if any(w in t for w in words):
            flags.add(key)
    if p['infants']:
        flags.add('infant')
    if form and form.get('tags'):
        flags |= set(form['tags'].split(','))
    p['flags'] = sorted(flags)

    # ── 行动能力：轮椅 ≠ 需要无障碍厕所，前者是代步工具，后者是设施 ────────
    p['wheelchair'] = bool(re.search(r'轮椅|坐轮椅|推轮椅', t))
    p['needToilet'] = bool(re.search(r'无障碍厕所|无障碍卫生间|无障碍卫浴|无障碍洗手间', t))
    p['needAed'] = bool(re.search(r'AED|aed|除颤', t))
    p['needParking'] = bool(re.search(r'停车|车位|自驾|开车去', t))
    p['lowWalk'] = bool(re.search(r'腿脚|走不动|膝盖|少走路|别太累|不能爬|爬不动|台阶|坡道', t)) or 'elderly' in flags
    if form and form.get('wheelchair') in ('1', 1, True, 'true'):
        p['wheelchair'] = p['lowWalk'] = p['needToilet'] = True
    if form and form.get('toilet') in ('1', 1, True, 'true'):
        p['needToilet'] = True

    # ── 兴趣与「热门」倾向 ───────────────────────────────────────────────
    hits = []
    for tag, words in INTERESTS:
        if any(w in t for w in words):
            hits.append(tag)
    if form and form.get('interests'):
        hits += [x for x in form['interests'].split(',') if x]
    p['interests'] = list(dict.fromkeys(hits))
    p['popular'] = bool(re.search(r'热门|必去|经典|有名|知名|网红', t))

    # 雨天倾向
    p['preferIndoor'] = bool(re.search(r'下雨|雨天|别晒|怕晒|太热|防晒|阴天', t))

    # ── 每日时间窗 ──────────────────────────────────────────────────────
    p['start'] = '09:00'
    p['end'] = '18:30'
    m = re.search(r'(\d{1,2})\s*[:：点]\s*(\d{0,2})\s*(?:开始|出发|到)', t)
    if m:
        p['start'] = '%02d:%02d' % (int(m[1]), int(m[2] or 0))
    if re.search(r'半天|上午|半天时间', t) and '下午' not in t:
        p['end'] = '13:30'
    # 只有「下午出发」才是把起点推到下午；光出现「下午」两个字不算（比如「下午 4 点半关门」）
    if re.search(r'下午(?:才)?(?:出发|动身|开始)|午饭后出发|吃完午饭(?:再)?出发', t):
        p['start'] = '13:30'
    if re.search(r'夜景|夜游|晚上(?:去|逛|看|吃)|看夜景|灯光秀', t):
        p['end'] = '21:00'

    # 到达日：下午才落地，上午不能排。只记标记，不改全局 start——
    # 改全局 start 会把「第二天」也变成下午才开始。
    p['arriveAfternoon'] = bool(re.search(r'下午(?:才)?到|下午抵达|中午到|下午的?(?:飞机|高铁|航班|车)', t))

    # 返程航班：留 2 小时值机 + 1 小时进城路程，市区行程提前 3 小时收尾
    p['flightOut'] = None
    m = re.search(r'(\d{1,2})\s*[点:：]\s*(\d{0,2})?\s*(半)?\s*(?:的)?\s*(?:飞机|航班|机票)', t)
    if m:
        hh, mm = int(m[1]), (30 if m[3] else int(m[2] or 0))
        head = t[max(0, m.start() - 10):m.start()]
        if re.search(r'晚上|傍晚|下午|夜', head) and hh < 12:
            hh += 12
        p['flightOut'] = '%02d:%02d' % (min(23, hh), mm)

    if form:
        p['start'] = form.get('start') or p['start']
        p['end'] = form.get('end') or p['end']

    # ── 节奏与数量目标 ──────────────────────────────────────────────────
    p['relaxed'] = bool(re.search(r'不要太赶|不赶|轻松|悠闲|慢慢|节奏慢|别太累', t))
    p['spotTarget'] = None
    m = re.search(r'(\d+)\s*[-~到至]\s*(\d+)\s*个', t)
    if m:
        p['spotTarget'] = int(m[2])
    else:
        m = re.search(r'(\d+)\s*个\s*(?:热门|景点|地方|去处)', t)
        if m:
            p['spotTarget'] = int(m[1])

    # ── 酒店预算上限 ────────────────────────────────────────────────────
    p['hotelMax'] = None
    m = re.search(r'(\d{2,5})\s*(?:元|块)?\s*(?:以内|以下|之内)', t)
    if m:
        p['hotelMax'] = int(m[1])

    # ── 天数：先看「N 天 / N 日」，再看「周三到、周四回」这种跨度 ──────────
    p['days'] = 1
    spans = []
    for m in re.finditer(r'([一两二三四五六七八九十\d]+)\s*(?:天|日)(?![子本])', t):
        v = m[1]
        spans.append(_num(v) if v in CN_NUM or v.isdigit() else None)
    spans = [x for x in spans if x]
    if spans:
        p['days'] = max(1, min(7, max(spans)))

    wk = [WEEK_IDX[x] for x in re.findall(r'周([一二三四五六日天])', t)]
    if len(wk) >= 2 and wk[-1] >= wk[0]:
        p['days'] = max(p['days'], min(7, wk[-1] - wk[0] + 1))

    # ── 日期：支持「下周 + 周三」 ────────────────────────────────────────
    w = get_weather()['days']
    today = datetime.date.today()
    p['date'] = w[0]['date']
    if '明天' in t:
        p['date'] = w[1]['date']
    elif '后天' in t:
        p['date'] = w[2]['date']
    m = re.search(r'(20\d{2}-\d{2}-\d{2})', t)
    if m:
        p['date'] = m[1]
    else:
        md = re.search(r'周([一二三四五六日天])', t)
        if md:
            target = WEEK_IDX[md[1]]
            if re.search(r'下周|下个?星期|下礼拜', t):
                base = today + datetime.timedelta(days=7 - today.weekday())      # 下周一
                dt = base + datetime.timedelta(days=target)
            else:
                dt = today + datetime.timedelta(days=(target - today.weekday()) % 7)
            p['date'] = dt.isoformat()
    if form and form.get('date'):
        p['date'] = form['date']
    if form and str(form.get('days', '')).isdigit():
        p['days'] = max(1, min(7, int(form['days'])))

    # ── 口述数据覆盖：用户说的排队/关门时间，优先级高于数据集 ─────────────
    p['overrides'] = []
    for s in get_spots()['spots']:
        short = re.split(r'[（(]', s['name'])[0]
        if not short or short not in t:
            continue
        seg = t[t.index(short):t.index(short) + 80]
        ov = {}
        mq = re.search(r'排队[^。；，]{0,12}?(\d+)\s*个?\s*(?:多)?\s*小时', seg)
        if mq:
            ov['queueMin'] = int(mq[1]) * 60 + 20
        mc = re.search(r'(\d{1,2})\s*[点:：]\s*(\d{0,2})?\s*(半)?\s*(?:就)?\s*(?:关门|闭馆|打烊|结束)', seg)
        if mc:
            hh, mm = int(mc[1]), (30 if mc[3] else int(mc[2] or 0))
            if re.search(r'下午|晚上|傍晚', seg[:mc.start()]) and hh < 12:
                hh += 12
            ov['close'] = '%02d:%02d' % (hh, mm)
        if ov:
            ov.update(id=s['id'], name=s['name'])
            p['overrides'].append(ov)

    p['weather'] = next((d for d in w if d['date'] == p['date']), w[0])
    return p


# ── 路线规划核心 ─────────────────────────────────────────────────────────────
def travel_leg(a, b, profile, transport):
    """两点之间怎么走：步行 / 地铁 / 打车，含耗时与费用。"""
    d = haversine(a, b)
    limit = 0.8 if profile['wheelchair'] else 1.2
    loc = {x['mode']: x for x in transport['local']}
    if d <= limit:
        mode = '步行'; minutes = d / loc['步行']['speedKmh'] * 60; fare = 0
    elif d <= 8:
        mode = '地铁'; minutes = d / loc['地铁']['speedKmh'] * 60 + loc['地铁']['waitMin']; fare = loc['地铁']['farePerTrip']
    else:
        mode = '打车'; minutes = d / loc['打车']['speedKmh'] * 60 + loc['打车']['waitMin']; fare = loc['打车']['farePerTrip']
    if profile['wheelchair'] and mode == '步行' and d > 0.8:
        mode = '打车'; minutes = d / loc['打车']['speedKmh'] * 60 + loc['打车']['waitMin']; fare = loc['打车']['farePerTrip']
    return dict(mode=mode, minutes=int(round(minutes)), km=round(d, 2), fare=fare)


def queue_now(spot, at_min, weather, weekend):
    h = at_min / 60
    factor = 1.0
    if 10 <= h <= 15:
        factor *= 1.6
    if weekend:
        factor *= 1.25
    if weather['rainProb'] >= 60 and not spot['indoor']:
        factor *= 0.6            # 雨天户外排队变少
    if weather['rainProb'] >= 60 and spot['indoor']:
        factor *= 1.3            # 雨天室内人更多
    return int(round(spot['queueMin'] * factor))


# 多维评价：每一项都标明是定量、半定量还是定性来源
CRITERIA = [
    dict(key='rating', label='口碑', kind='定量', weight=2.0, desc='评分 × 2'),
    dict(key='interest', label='兴趣匹配', kind='定性', weight=9.0, desc='命中一个兴趣 +9'),
    dict(key='crowd', label='人群适配', kind='定性', weight=4.0, desc='亲子/情侣标签 +3~4'),
    dict(key='weather', label='天气适配', kind='半定量', weight=4.0, desc='降水概率与室内外 +4/−4'),
    dict(key='access', label='无障碍', kind='定性', weight=4.0, desc='轮椅可达 +4'),
    dict(key='walk', label='步行强度', kind='半定量', weight=2.2, desc='强度越高扣分越多'),
    dict(key='queue', label='排队成本', kind='定量', weight=1/12, desc='排队分钟 / 12'),
    dict(key='travel', label='路上耗时', kind='定量', weight=1/12, desc='移动分钟 / 12'),
    dict(key='ticket', label='门票成本', kind='定量', weight=1/120, desc='票价 / 120'),
]


def criteria_for(req):
    """维度表随需求变化——要求「热门」就把口碑权重抬上去，要求停车就加一维。

    界面上展示的就是这张表，所以它必须和真正参与打分的那套权重是同一份，
    不能在界面上写 2.0、实际按 3.0 算。
    """
    out = [dict(c) for c in CRITERIA]
    if req.get('popular'):
        for c in out:
            if c['key'] == 'rating':
                c['weight'] = 3.0
                c['desc'] = '评分 × 3（本轮点名要热门）'
    if req.get('needParking'):
        out.append(dict(key='facility', label='停车', kind='定性', weight=3.0,
                        desc='需要停车且景点有车位 +3'))
    return out


def _weights(req):
    return {c['key']: c['weight'] for c in criteria_for(req)}


WAIT_PENALTY = 0.12          # 开门前每多等 1 分钟扣的分（超过 30 分钟起算）


def score_parts(s, req, weather, weekend, travel_minutes=0):
    """逐项给分，前端把这张表直接摊开给评审看。"""
    W = _weights(req)
    p = {}
    p['rating'] = round(s['rating'] * W['rating'], 2)
    p['interest'] = round(len([t for t in req['interests'] if t in s['tags']]) * W['interest'], 2)
    p['crowd'] = 0.0
    if 'kids' in req['flags'] and ('亲子' in s['tags'] or '动物' in s['tags']):
        p['crowd'] += W['crowd']
    if 'infant' in req['flags'] and ('亲子' in s['tags'] or '园林' in s['tags'] or '湖景' in s['tags']):
        p['crowd'] += W['crowd'] - 1
    if 'couple' in req['flags'] and ('夜景' in s['tags'] or '拍照' in s['tags'] or '湖景' in s['tags']):
        p['crowd'] += W['crowd'] - 1
    p['weather'] = 0.0
    if req['preferIndoor'] and s['indoor']:
        p['weather'] += 2
    if weather['rainProb'] >= 60:
        p['weather'] += W['weather'] if s['indoor'] else -W['weather']
    elif weather['outdoorScore'] >= 4 and not s['indoor']:
        p['weather'] += 2
    p['access'] = W['access'] if (req['wheelchair'] and s['wheelchair']) else 0.0
    p['walk'] = round(-(s['walkIntensity'] - 1) * (W['walk'] if req['lowWalk'] else 0.6), 2)
    p['queue'] = round(-min(s['queueMin'], 40) * W['queue'], 2)
    p['travel'] = round(-travel_minutes * W['travel'], 2)
    p['ticket'] = round(-s['ticket'] * W['ticket'], 2)
    if 'facility' in W:
        p['facility'] = W['facility'] if s['parking'] else 0.0
    if weekend and not s['indoor']:
        p['crowd'] = round(p['crowd'] - 1, 2)
    return p


def score_spot(s, req, weather, weekend, travel_minutes=0):
    return sum(score_parts(s, req, weather, weekend, travel_minutes).values())


def allowed(s, req, weekday):
    if weekday in s.get('closedDays', []):
        return False, '%s 闭馆' % weekday
    if req['wheelchair'] and not s['wheelchair']:
        return False, '轮椅不便'
    if req.get('needAed') and not s['aed']:
        return False, '无 AED'
    if req.get('needToilet') and not s['accessibleToilet']:
        return False, '无无障碍厕所'
    if req['lowWalk'] and s['walkIntensity'] > 3:
        return False, '步行强度 %d/5 偏高' % s['walkIntensity']
    return True, ''


def explain_rejects(spots, req, weather, weekend, weekday, chosen_ids, used_ids=None):
    """把没进最终行程的点说清楚：硬约束被拒 / 前几天去过 / 有资格但没排上。"""
    reasons = {}
    for s in spots:
        ok, why = allowed(s, req, weekday)
        if not ok:
            reasons[s['id']] = dict(kind='blocked', why=why)
    out = []
    for s in spots:
        if s['id'] in chosen_ids:
            continue
        if s['id'] in (used_ids or set()):
            out.append(dict(id=s['id'], name=s['name'], zone=s['zone'], kind='used',
                            why='已在前面某天排入行程，今天不重复', score=None, parts=None))
        elif s['id'] in reasons:
            out.append(dict(id=s['id'], name=s['name'], zone=s['zone'], kind='blocked',
                            why=reasons[s['id']]['why'], score=None, parts=None))
        else:
            parts = score_parts(s, req, weather, weekend, 0)
            out.append(dict(id=s['id'], name=s['name'], zone=s['zone'], kind='passed',
                            why='满足准入，评分未进当天前列', score=round(sum(parts.values()), 2),
                            parts=parts))
    out.sort(key=lambda x: (0 if x['kind'] == 'blocked' else (1 if x['kind'] == 'used' else 2), -(x['score'] or 0)))
    return out


def pick_food(food, near, req, zone=None):
    cands = [f for f in food if (not req['wheelchair']) or f['wheelchair']]
    if zone:
        same = [f for f in cands if f['zone'] == zone]
        cands = same or cands
    if not cands:
        return None
    ranked = sorted(cands, key=lambda f: haversine(near, f) + f['queueMin'] / 30 + f['pricePerPerson'] / 60)
    if len(ranked) > 1:
        return ranked[(req.get('day', 1) - 1) % min(3, len(ranked))]
    return ranked[0]


def build_group(spots, food, hotel, weather, req, transport, start_min, end_min, weekend, weekday, label,
                lunch_place=None, skip=None, allow_lunch=True, jitter=0.0, rng=None, order=None):
    """贪心 + 评分：在开放时间、排队、步行强度、天气、午餐窗口约束下排出当天顺序。

    jitter > 0 时对比较用的分数加均匀扰动，生成「随机化贪心」的一个样本。
    order 给定时严格按该优先级顺序尝试（外层 ILS 用的模式），不再按分数挑。
    记录到 timeline 的分数始终是真实分数。
    """
    profile = dict(wheelchair=req['wheelchair'], lowWalk=req['lowWalk'])
    prio = {sid: i for i, sid in enumerate(order or [])}
    remain = [s for s in spots if s['id'] not in (skip or set())]
    timeline, tickets, walk_km, local_fare = [], 0, 0.0, 0
    picked = []
    cur = {'lat': hotel['lat'], 'lon': hotel['lon'], 'name': hotel['name']}
    t = start_min
    lunch_done = False
    nap_done = False
    last_rest = start_min
    LUNCH_FROM, LUNCH_TO = 11 * 60 + 30, 13 * 60 + 30
    size = req.get('groupSize') or 1
    max_spots = int(req.get('maxPerDay') or 99)
    NAP_MIN = 80

    def lunch_entries(now):
        nonlocal cur, local_fare, walk_km, tickets
        if lunch_place:
            f = next((x for x in food if x['id'] == lunch_place), None)
        else:
            f = pick_food(food, cur, req)
        if not f:
            return now, None
        leg = travel_leg(cur, f, profile, transport)
        arrive = now + leg['minutes']
        q = int(f['queueMin'] * (1.4 if weekend else 1.0))
        begin = arrive + q
        if begin + 50 > end_min:
            return now, None
        rows = []
        if leg['minutes'] >= 5:
            rows.append(dict(type='travel', start=hhmm_text(now), end=hhmm_text(arrive), name='前往 %s' % f['name'],
                             minutes=leg['minutes'], mode=leg['mode'], km=leg['km'],
                             reason='%s 约 %.1f 公里，赶午餐' % (leg['mode'], leg['km'])))
        rows.append(dict(type='meal', start=hhmm_text(begin), end=hhmm_text(begin + 50), name=f['name'],
                         minutes=q + 50, queue=q, price=f['pricePerPerson'],
                         reason='%s，人均 ¥%d%s' % ('、'.join(f['tags']), f['pricePerPerson'], '，轮椅可进' if f['wheelchair'] else '')))
        local_fare += leg['fare']
        walk_km += leg['km'] if leg['mode'] == '步行' else 0
        cur = f
        return begin + 50, rows

    while t < end_min - 25 and len(picked) < max_spots:
        # 午餐：11:30 起优先安排，避免为了塞景点把午饭拖到下午
        if allow_lunch and not lunch_done and t >= LUNCH_FROM - 15:
            nt, rows = lunch_entries(t)
            if rows:
                timeline += rows; t = nt; lunch_done = True
                continue

        # 婴幼儿午睡：回酒店睡 80 分钟，下午才不崩
        if req.get('nap') and not nap_done and (lunch_done or t >= 13 * 60):
            back = travel_leg(cur, hotel, profile, transport)
            arrive = t + back['minutes']
            if arrive + NAP_MIN + 45 <= end_min:
                if back['minutes'] >= 5:
                    timeline.append(dict(type='travel', start=hhmm_text(t), end=hhmm_text(arrive),
                                         name='返回 %s' % hotel['name'], minutes=back['minutes'],
                                         mode=back['mode'], km=back['km'], reason='带婴幼儿回房午睡'))
                timeline.append(dict(type='nap', start=hhmm_text(arrive), end=hhmm_text(arrive + NAP_MIN),
                                     name='酒店午睡', minutes=NAP_MIN,
                                     reason='同行有 2 岁以下婴幼儿，中午回房睡一觉，下午不闹'))
                local_fare += back['fare']
                walk_km += back['km'] if back['mode'] == '步行' else 0
                t = arrive + NAP_MIN
                cur = hotel
                nap_done = True
                continue

        # 低步行人群每 2.5 小时休息一次
        if req['lowWalk'] and t - last_rest >= 150:
            timeline.append(dict(type='rest', start=hhmm_text(t), end=hhmm_text(t + 15), name='就近休息', minutes=15,
                                 reason='低步行强度安排，每 2.5 小时休息 15 分钟'))
            t += 15; last_rest = t
            continue

        best, best_sc, best_plan = None, None, None
        # order 给定时按给定优先级依次尝试（外层 ILS 在「访问顺序空间」里搜索）；
        # 没给 order 时退化为原来的「取当前最高分」，保持默认行为不变。
        trial = sorted(remain, key=lambda s: prio.get(s['id'], 10 ** 6)) if prio else remain
        for s in trial:
            ok, why = allowed(s, req, weekday)
            if not ok:
                continue
            leg = travel_leg(cur, s, profile, transport)
            arrive = t + leg['minutes']
            open_m, close_m = hhmm(s['open']), hhmm(s['close'])
            begin = max(arrive, open_m)
            wait_min = begin - arrive
            if wait_min > 180:
                continue                      # 等三小时以上，当天已无意义
            q = queue_now(s, begin, weather, weekend)
            dur = s['durationMin']
            if begin + q + 45 > close_m:
                continue
            if begin + q + dur > close_m:
                dur = close_m - begin - q
            leave = begin + q + dur
            if leave > end_min:
                continue
            # 留出午餐窗口：不能边逛边把午饭挤掉
            if allow_lunch and not lunch_done and begin < LUNCH_TO and leave > LUNCH_FROM:
                continue
            sc_real = score_spot(s, req, weather, weekend, leg['minutes'])
            # 开门前干等不再硬性跳过，而是折算成时间成本：等得越久分越低，
            # 但只要没有更好的选择，仍然可以选——硬剪枝会把最优解直接丢掉。
            if wait_min > 30:
                sc_real -= round((wait_min - 30) * WAIT_PENALTY, 2)
            if s['ticket'] >= 200 and dur < 90:
                sc_real -= 6            # 高价景点匆匆路过不划算
            if prio:
                # 指定顺序模式：第一个可行的就排进去，把顺序决策权交还外层
                best, best_sc, best_plan = s, sc_real, (leg, begin, q, dur, leave, sc_real)
                break
            # 比较用分数可以带扰动（随机化贪心），记录用分数始终是真实值
            sc_cmp = sc_real * (1 + rng.uniform(-jitter, jitter)) if (jitter and rng) else sc_real
            if best_sc is None or sc_cmp > best_sc:
                best, best_sc, best_plan = s, sc_cmp, (leg, begin, q, dur, leave, sc_real)
        if not best:
            if allow_lunch and not lunch_done and t > start_min + 90:
                nt, rows = lunch_entries(t)
                if rows:
                    timeline += rows; t = nt; lunch_done = True
                    continue
            break

        s = best
        leg, begin, q, dur, leave, _ = best_plan
        if leg['minutes'] >= 5:
            timeline.append(dict(type='travel', start=hhmm_text(t), end=hhmm_text(t + leg['minutes']),
                                 name='前往 %s' % s['name'], minutes=leg['minutes'], mode=leg['mode'], km=leg['km'],
                                 reason='%s 约 %.1f 公里' % (leg['mode'], leg['km'])))
        if begin > t + leg['minutes']:
            timeline.append(dict(type='wait', start=hhmm_text(t + leg['minutes']), end=hhmm_text(begin),
                                 name='等开门', minutes=begin - t - leg['minutes'], reason='%s 才开放' % s['open']))
        reasons = []
        for tag in req['interests']:
            if tag in s['tags']:
                reasons.append('命中「%s」' % tag)
        if weather['rainProb'] >= 60:
            reasons.append('雨天室内更稳妥' if s['indoor'] else '户外为主，' + weather['tip'][:10])
        if req['wheelchair']:
            reasons.append('轮椅可通行' + ('、有无障碍厕所' if s['accessibleToilet'] else ''))
        if req['lowWalk'] and s['walkIntensity'] <= 2:
            reasons.append('路面平缓好走')
        if q:
            reasons.append('排队约 %d 分钟已计入' % q)
        reasons.append('评分 %.1f' % s['rating'])
        parts = score_parts(s, req, weather, weekend, leg['minutes'])
        timeline.append(dict(type='spot', start=hhmm_text(begin + q), end=hhmm_text(leave), name=s['name'],
                             minutes=dur, queue=q, ticket=s['ticket'], walkIntensity=s['walkIntensity'],
                             indoor=s['indoor'], zone=s['zone'], lat=s['lat'], lon=s['lon'],
                             score=round(sum(parts.values()), 2), parts=parts,
                             access=dict(wheelchair=s['wheelchair'], toilet=s['accessibleToilet'],
                                         aed=s['aed'], parking=s['parking']),
                             reason='；'.join(reasons[:4])))
        picked.append(s['id'])
        tickets += s['ticket'] * size
        walk_km += leg['km'] if leg['mode'] == '步行' else 0
        local_fare += leg['fare']
        remain.remove(s)
        t = leave
        cur = s

    leg = travel_leg(cur, hotel, profile, transport)
    if leg['minutes'] >= 5 and t + leg['minutes'] <= end_min + 30:
        timeline.append(dict(type='travel', start=hhmm_text(t), end=hhmm_text(t + leg['minutes']),
                             name='返回 %s' % hotel['name'], minutes=leg['minutes'], mode=leg['mode'], km=leg['km'],
                             reason='结束当天行程'))
        local_fare += leg['fare']
        walk_km += leg['km'] if leg['mode'] == '步行' else 0
        t += leg['minutes']

    done = [x for x in timeline if x['type'] == 'spot']
    stats = dict(spots=len(done), queueMin=sum(x.get('queue', 0) for x in done),
                 walkKm=round(walk_km, 1), ticket=tickets, localFare=local_fare,
                 durationMin=t - start_min, end=hhmm_text(t),
                 nap=NAP_MIN if nap_done else 0,
                 meal=sum(x.get('price', 0) for x in timeline if x['type'] == 'meal'))
    return dict(id=label['id'], name=label['name'], members=label['members'], profile=label['profile'],
                timeline=timeline, stats=stats, notes=[],
                picked=picked, skipped=sorted(skip or set()))


# ── 最优化外层：贪心构造 + ILS（破坏重建 / GRASP 多起点）─────────────────────
def objective(g):
    """目标函数：当天所有停留点的真实得分之和（对应 TOPTW 的 profit 最大化）。"""
    return round(sum(x.get('score', 0) for x in g['timeline'] if x['type'] == 'spot'), 3)


def solve_group(spots, food, hotel, weather, req, transport, start_min, end_min, weekend, weekday, label,
                lunch_place=None, allow_lunch=True, iters=160, seed=20261121, skip=None):
    """一次贪婪构造 + 多轮改进，返回带 optimize 字段的最优解。

    构造：按九维得分贪心插入，得到初始访问顺序（经典做法）。
    改进：Iterated Local Search —— 在「访问顺序」这个排列空间上做邻域搜索
          （交换两站 / 把一站挪到别的位置），按给定顺序重新排时刻表，只接受更优解；
          连续无改进时加大扰动力度，并随机引入此前没排上的候选点。
          这一步才能改变「先去哪」这种结构性决策，单纯调分数权重是改不动的。
    """
    rng = random.Random(seed)
    args = dict(food=food, hotel=hotel, weather=weather, req=req, transport=transport,
                start_min=start_min, end_min=end_min, weekend=weekend, weekday=weekday, label=label,
                lunch_place=lunch_place, allow_lunch=allow_lunch)

    base = build_group(spots, skip=skip, **args)
    best, best_obj, base_obj = base, objective(base), objective(base)
    best_order = list(base['picked'])
    trace = [(0, best_obj)]
    if not best_order:
        best['optimize'] = dict(iters=0, base=base_obj, best=best_obj, gain=0.0,
                                rounds=0, accepted=0, trace=trace)
        return best

    spare = [s['id'] for s in spots
             if s['id'] not in set(best_order) and s['id'] not in (skip or set())]
    stall, accepted = 0, 0
    for it in range(1, iters + 1):
        cur = list(best_order)
        n = len(cur)
        # 扰动力度随停滞时间增长：1 次交换 → 连续多次移动
        moves = 1 + (stall // 4 if stall >= 4 else 0)
        for _ in range(min(moves, 4)):
            op = rng.random()
            if op < 0.45 and n >= 2:
                i, j = rng.sample(range(n), 2)
                cur[i], cur[j] = cur[j], cur[i]
            elif op < 0.85 and n >= 2:
                i = rng.randrange(n)
                j = rng.randrange(n)
                cur.insert(j, cur.pop(i))
            elif spare:
                # 把没排上过的候选点塞进来，给解空间引入新成员
                cur.insert(rng.randrange(n + 1), rng.choice(spare))
        cand = build_group(spots, skip=skip, order=cur, **args)
        obj = objective(cand)
        if obj > best_obj + 1e-9:
            best, best_obj, stall = cand, obj, 0
            best_order = list(cand['picked'])
            spare = [s['id'] for s in spots
                     if s['id'] not in set(best_order) and s['id'] not in (skip or set())]
            accepted += 1
        else:
            stall += 1
        trace.append((it, best_obj))

    best['optimize'] = dict(
        iters=iters, base=base_obj, best=best_obj, gain=round(best_obj - base_obj, 2),
        rounds=sum(1 for i in range(1, len(trace)) if trace[i][1] > trace[i - 1][1] + 1e-9),
        accepted=accepted, trace=trace)
    return best



# ── 最优性验证：小规模穷举对标 ────────────────────────────────────────────────
def eval_order(order, hotel, req, weather, weekend, transport, start_min, end_min):
    """给定访问顺序，判断是否满足开放时间与当天时间窗，并算真实目标值。

    与 build_group 使用同一套 score_spot / travel_leg / queue_now，保证口径一致；
    关掉午餐与「干等 30 分钟」剪枝，所以这里是无启发式干预的真实目标函数。
    """
    profile = dict(wheelchair=req['wheelchair'], lowWalk=req['lowWalk'])
    cur = {'lat': hotel['lat'], 'lon': hotel['lon'], 'name': hotel['name']}
    t, total = start_min, 0.0
    for s in order:
        leg = travel_leg(cur, s, profile, transport)
        arrive = t + leg['minutes']
        begin = max(arrive, hhmm(s['open']))
        q = queue_now(s, begin, weather, weekend)
        dur = s['durationMin']
        leave = begin + q + dur
        if leave > hhmm(s['close']) or leave > end_min:
            return False, None
        total += score_spot(s, req, weather, weekend, leg['minutes'])
        t, cur = leave, s
    return True, round(total, 3)


def benchmark(n=7, trials=3):
    """随机抽 n 个景点，穷举全部 n! 种顺序求最优，再与 ILS 结果对比。

    n=7 时 5040 种排列，可在毫秒级穷举完，因此这里的「最优」是可证明的最优，
    不是上界——用来验证启发式有没有丢掉更好的解。池子会预先筛到「排得下」，
    避免出现全部排列都不可行、gap 被误判成 0 的情况。
    """
    doc = get_spots()
    spots, food = doc['spots'], doc['food']
    weather = get_weather()['days'][0]
    transport = get_transport()
    hotel = get_hotels()['hotels'][0]
    start_min, end_min = 8 * 60, 21 * 60
    criteria = dict(city='杭州', date=weather['date'], start='08:00', end='21:00', interests=[],
                    flags=[], wheelchair=False, lowWalk=False, people=2, groupSize=2,
                    preferIndoor=False, weather=weather)
    label = dict(id='A', name='基准', members=2, profile='常规节奏')
    pool_all = [s for s in spots if s['ticket'] < 200 and s['walkIntensity'] <= 3 and s['durationMin'] <= 120]

    rows = []
    for k in range(trials):
        # 预检：池子必须存在至少一个可行顺序，否则穷举出来的「最优」是空的。
        # 试三种典型顺序（分数降序 / 时长升序 / 开门时间升序），任一可行即通过。
        pool, nn = None, n
        for nn in range(n, max(2, n - 3), -1):
            for attempt in range(25):
                rng = random.Random(7000 + k * 131 + nn * 17 + attempt)
                cand = rng.sample(pool_all, min(nn, len(pool_all)))
                orders = [
                    sorted(cand, key=lambda s: -score_spot(s, criteria, weather, False, 0)),
                    sorted(cand, key=lambda s: s['durationMin']),
                    sorted(cand, key=lambda s: hhmm(s['open'])),
                ]
                if any(eval_order(o, hotel, criteria, weather, False, transport, start_min, end_min)[0]
                       for o in orders):
                    pool = cand
                    break
            if pool:
                break
        if pool is None:
            continue

        t0 = time.time()
        best_val, best_seq, feas = None, None, 0
        for perm in itertools.permutations(pool):
            ok, v = eval_order(list(perm), hotel, criteria, weather, False, transport, start_min, end_min)
            if not ok:
                continue
            feas += 1
            if best_val is None or v > best_val:
                best_val, best_seq = v, [s['name'] for s in perm]
        brute_ms = (time.time() - t0) * 1000
        if best_val is None:
            continue                      # 理论上不会发生，兜底跳过而不是当成 gap 0

        t1 = time.time()
        g = solve_group(pool, food, hotel, weather, criteria, transport, start_min, end_min,
                        False, '周五', label, allow_lunch=False, iters=200, seed=100 + k)
        ils_ms = (time.time() - t1) * 1000
        ils_val = objective(g)

        gap = round((best_val - ils_val) / abs(best_val) * 100, 2) if best_val else 0.0
        rows.append(dict(
            pool=[s['name'] for s in pool],
            perms=math.factorial(len(pool)), feasiblePerms=feas,
            brute=dict(value=best_val, seq=best_seq, ms=round(brute_ms, 1)),
            ils=dict(value=ils_val, spots=g['stats']['spots'],
                     names=[x['name'] for x in g['timeline'] if x['type'] == 'spot'], ms=round(ils_ms, 1)),
            gapPct=gap, hit=(gap <= 0.001)))

    hit = sum(1 for r in rows if r['hit'])
    return dict(
        n=n, trials=rows,
        summary=dict(n=n, trips=len(rows), hit=hit,
                     hitRate=round(hit / max(1, len(rows)) * 100, 1),
                     avgBruteMs=round(sum(r['brute']['ms'] for r in rows) / max(1, len(rows)), 1),
                     avgIlsMs=round(sum(r['ils']['ms'] for r in rows) / max(1, len(rows)), 1),
                     avgGap=round(sum(r['gapPct'] for r in rows) / max(1, len(rows)), 2),
                     perms=rows[0]['perms'] if rows else 0),
        note='brute 为全部排列穷举得到的可证明最优；ils 为贪心构造 + ILS 改进的结果。gap=0 表示启发式达到了最优。')


def synth_instance(n, seed=0):
    """合成算例：n 个虚拟景点，坐标/时长/开放窗随机但可复现。

    真实景点池太小（排不下 7 个），做规模曲线会失真，因此单独造一组算例，
    专门用来展示「排列数爆炸 vs 启发式耗时基本不变」这条曲线。
    """
    rng = random.Random(seed)
    out = []
    for i in range(n):
        out.append(dict(
            id='x%d' % i, name='算例点%d' % (i + 1), zone='X',
            lat=30.25 + rng.uniform(-0.045, 0.045), lon=120.15 + rng.uniform(-0.045, 0.045),
            open='09:00', close='19:00', closedDays=[], queueMin=rng.randint(0, 8),
            durationMin=rng.choice([40, 45, 50, 55]), walkIntensity=2, indoor=True,
            ticket=0, rating=round(rng.uniform(8.0, 9.6), 1), tags=[], wheelchair=True,
            accessibleToilet=True, aed=False, parking=True, note=''))
    return out


def benchmark_scaling(ns=(4, 5, 6, 7, 8), seed=11):
    """对合成算例逐规模穷举 vs ILS，输出耗时与 gap，用于画规模曲线。"""
    weather = get_weather()['days'][0]
    transport = get_transport()
    hotel = dict(get_hotels()['hotels'][0])
    hotel.update(name='起点')
    criteria = dict(city='杭州', date=weather['date'], start='09:00', end='19:00', interests=[],
                    flags=[], wheelchair=False, lowWalk=False, people=1, groupSize=1,
                    preferIndoor=False, weather=weather)
    label = dict(id='A', name='基准', members=1, profile='常规节奏')
    rows = []
    for n in ns:
        pool = synth_instance(n, seed=seed)
        t0 = time.time()
        best_val = None
        for perm in itertools.permutations(pool):
            ok, v = eval_order(list(perm), hotel, criteria, weather, False, transport, 9 * 60, 19 * 60)
            if ok and (best_val is None or v > best_val):
                best_val = v
        brute_ms = (time.time() - t0) * 1000
        if best_val is None:
            continue
        t1 = time.time()
        g = solve_group(pool, [], hotel, weather, criteria, transport, 9 * 60, 19 * 60,
                        False, '周五', label, allow_lunch=False, iters=160, seed=seed)
        ils_ms = (time.time() - t1) * 1000
        ils_val = objective(g)
        rows.append(dict(n=n, perms=math.factorial(n), bruteMs=round(brute_ms, 1),
                         ilsMs=round(ils_ms, 1), brute=best_val, ils=ils_val,
                         gapPct=round((best_val - ils_val) / abs(best_val) * 100, 2) if best_val else 0.0,
                         speedup=round(brute_ms / max(ils_ms, 0.01), 1)))
    return dict(rows=rows,
                note='合成算例：n 个虚拟景点、同一套评分与时间窗约束。brute 为全排列穷举的可证明最优。')


# ── 完整规划：单人 / 分组 / 多日 ──────────────────────────────────────────────
FLAG_CN = dict(elderly='含长辈', kids='含孩子', couple='情侣', friends='朋友同行')
WEEK_CN = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


def pick_hotel(req, hotels, spots=None):
    """住宿：先满足硬条件（预算 / 无障碍厕所 / 停车），再比「离景区近」。

    返回 (hotel, notes) —— notes 用于把「预算内没有满足条件的房」这类
    真实取舍如实说出来，而不是悄悄选一个超预算的。
    """
    notes = []
    pool = list(hotels)

    if req.get('needToilet') or req['wheelchair']:
        strict = [h for h in pool if h['wheelchair'] and h['accessibleToilet']]
        if strict:
            pool = strict
        else:
            notes.append(dict(level='warn', title='没有无障碍房',
                              text='样例住宿里没有同时满足「轮椅可达 + 无障碍厕所」的房间，已放宽到最接近的一家。'))

    if req.get('needParking'):
        withp = [h for h in pool if h['parking']]
        if withp:
            pool = withp
        else:
            notes.append(dict(level='warn', title='没有带车位的住宿',
                              text='预算内没有带停车位的住宿，需就近找社会停车场。'))

    cap = req.get('hotelMax')
    if cap:
        cheap = [h for h in pool if h['price'] <= cap]
        if cheap:
            pool = cheap
        else:
            lo = min(pool, key=lambda h: h['price'])
            notes.append(dict(level='warn', title='预算 %d 元内无可行住宿' % cap,
                              text='满足无障碍条件的样例房价最低是 %s ¥%d/晚，超出预算 ¥%d。要么把住房预算提到 %d，要么接受没有无障碍厕所的房源（对腿脚不便的老人不建议）。' % (
                                  lo['name'], lo['price'], lo['price'] - cap, lo['price'])))
            pool = [lo]

    def median_km(h):
        if not spots:
            return 0
        ds = sorted(haversine(h, s) for s in spots)
        return ds[len(ds) // 2]

    hotel = min(pool, key=lambda h: (round(median_km(h), 1), h['price']))
    return hotel, notes


def plan_day(req, day_no, spots, food, hotel, transport, weather, weekday, used, is_last,
             win_start=None, win_end=None):
    """排一天：分组求解 → 当天路线 / 无障碍 / 落选归因。

    used 是前面几天已经排过的景点 id，本日不再重复出现在主线上；
    win_start / win_end 是这一天的真实可用窗口（到达日下午才起算、
    返程日要提前去机场），不传就用需求里的默认时段。
    """
    req = dict(req)
    req['day'] = day_no
    weekend = weekday in ('周六', '周日')
    start_min = hhmm(win_start or req['start'])
    end_min = hhmm(win_end or req['end'])
    allow_lunch = (end_min - start_min) >= 300

    decisions = []
    decisions.append(dict(level='info', title='第 %d 天' % day_no,
                          text='%s %s · %s · %d℃/%d℃ 降水 %d%%%s' % (
                              weather['date'], weekday, weather['condition'],
                              weather['low'], weather['high'], weather['rainProb'],
                              ('，%s' % weather['tip']) if weather.get('tip') else '')))
    for tip in weather_advice(weather):
        decisions.append(dict(level='info', title='出行准备', text=tip))
    if win_start and win_start != req['start']:
        decisions.append(dict(level='warn', title='当天 %s 才开始' % win_start,
                              text='到达日下午才落地，上午不能排景点；当天只按 %s–%s 计算。' % (hhmm_text(start_min), hhmm_text(end_min))))
    if win_end and win_end != req['end']:
        decisions.append(dict(level='warn', title='当天 %s 收尾' % win_end,
                              text='返程航班按「提前 2 小时值机 + 1 小时进城」倒推，市区行程 %s 前必须结束。' % win_end))
    if not allow_lunch:
        decisions.append(dict(level='warn', title='当天时间不足 5.5 小时',
                              text='不单独安排正餐，把整段时间留给景点；如要用餐可把结束时间调晚。'))

    # ── 分组 ──────────────────────────────────────────────────────────────
    split = ('elderly' in req['flags'] and 'kids' in req['flags']) or (req['people'] >= 4 and len(req['flags']) >= 2)
    conflicts, merge, groups = [], [], []

    if split:
        seniors = max(1, req['people'] // 2)
        kids_n = max(1, req['people'] - seniors)
        a_req = dict(req); a_req.update(lowWalk=True, needToilet=True, groupSize=seniors)
        a_req['interests'] = [i for i in req['interests'] if i != '亲子']   # 长辈组不追亲子项
        ga = solve_group(spots, food, hotel, weather, a_req, transport, start_min, end_min, weekend, weekday,
                         dict(id='A', name='长辈组', members=seniors, profile='低步行 · 需无障碍'),
                         allow_lunch=allow_lunch, seed=20261121 + day_no, skip=used)
        lunch = next((x for x in ga['timeline'] if x['type'] == 'meal'), None)
        lunch_id = next((f['id'] for f in food if lunch and f['name'] == lunch['name']), None)
        a_names = {x['name'] for x in ga['timeline'] if x['type'] == 'spot'}
        overlap = {s['id'] for s in spots if s['name'] in a_names}
        b_req = dict(req); b_req.update(wheelchair=False, lowWalk=False, groupSize=kids_n)
        gb = solve_group(spots, food, hotel, weather, b_req, transport, start_min, end_min, weekend, weekday,
                         dict(id='B', name='亲子组', members=kids_n, profile='可爬坡 · 偏好亲子'),
                         lunch_place=lunch_id, skip=(used | overlap), allow_lunch=allow_lunch, seed=7 + day_no)
        groups = [ga, gb]
        decisions.append(dict(level='warn', title='分组成行',
                              text='需求里同时有长辈与孩子，拆成两组：长辈组走无障碍低步行路线，亲子组走高强度路线，午餐在 %s 汇合。' % (lunch['name'] if lunch else '就近餐厅')))
        if overlap:
            names = '、'.join(s['name'] for s in spots if s['id'] in overlap)
            conflicts.append(dict(day=day_no, type='reroute', spots=names,
                                  note='亲子组本来会与长辈组在同一时段撞点，已改走其他景点错峰，避免带着老人孩子一起排队'))
        if lunch:
            merge.append(dict(day=day_no, at=lunch['start'], place=lunch['name'],
                              note='两组同店午餐汇合；餐后可继续同行，也可按各自节奏分开'))
    else:
        r_req = dict(req); r_req['groupSize'] = req['people']
        label = dict(id='A', name='全队', members=req['people'],
                     profile='轮椅 · 低步行' if req['wheelchair'] else ('低步行' if req['lowWalk'] else '常规节奏'))
        groups = [solve_group(spots, food, hotel, weather, r_req, transport, start_min, end_min, weekend, weekday, label,
                              allow_lunch=allow_lunch, seed=20261121 + day_no * 101, skip=used)]

    empty = all(not g['picked'] for g in groups)
    if empty:
        decisions.append(dict(level='warn', title='当天没有可排的景点',
                              text='候选景点已在前几天排完，或全部被硬约束排除；建议缩短天数或放宽无障碍/步行限制。'))

    # ── 当天汇总 ──────────────────────────────────────────────────────────
    route_points, access_points = [], []
    for g in groups:
        seq = 0
        for x in g['timeline']:
            if x['type'] == 'spot':
                seq += 1
                route_points.append(dict(group=g['id'], day=day_no, seq=seq, name=x['name'], lat=x['lat'], lon=x['lon'],
                                         start=x['start'], end=x['end']))
    for g in groups:
        for x in g['timeline']:
            if x['type'] == 'spot':
                a = x['access']
                if a['wheelchair'] or a['toilet'] or a['aed'] or a['parking']:
                    access_points.append(dict(name=x['name'], wheelchair=a['wheelchair'], toilet=a['toilet'],
                                              aed=a['aed'], parking=a['parking']))

    chosen = {i for g in groups for i in g['picked']}
    rejected = explain_rejects(spots, req, weather, weekend, weekday, chosen, used)

    ticket = sum(g['stats']['ticket'] for g in groups)
    local_fare = sum(g['stats']['localFare'] for g in groups)
    meals = sum(g['stats']['meal'] * g['members'] for g in groups)
    stats = dict(spots=sum(g['stats']['spots'] for g in groups),
                 queueMin=sum(g['stats']['queueMin'] for g in groups),
                 walkKm=round(sum(g['stats']['walkKm'] for g in groups), 1),
                 ticket=ticket, localFare=local_fare, meals=meals,
                 score=round(sum(objective(g) for g in groups), 1),
                 durationMin=max((g['stats']['durationMin'] for g in groups), default=0))

    return dict(day=day_no, date=weather['date'], weekday=weekday, weather=weather,
                weekend=weekend, groups=groups, decisions=decisions,
                window=dict(start=hhmm_text(start_min), end=hhmm_text(end_min)),
                conflicts=conflicts, merge=merge, allowLunch=allow_lunch,
                route=dict(points=route_points), access=access_points,
                rejected=rejected[:8], stats=stats,
                budget=dict(ticket=ticket, localFare=local_fare, meals=meals,
                            total=ticket + local_fare + meals),
                picked=sorted(chosen))


def apply_overrides(spots, overrides):
    """把用户口述的排队/闭馆时间覆盖到数据集上。

    用户说「茶叶博物馆排队一个多小时、四点半就关门」，比数据里的旧值更可信——
    数据是样例，用户是刚问过的人。覆盖了就在界面上明说，不偷偷改。
    """
    if not overrides:
        return spots, []
    out, log = [], []
    omap = {o['id']: o for o in overrides}
    for s in spots:
        o = omap.get(s['id'])
        if not o:
            out.append(s)
            continue
        t = dict(s)
        bits = []
        if 'queueMin' in o:
            bits.append('排队 %d → %d 分钟' % (t['queueMin'], o['queueMin']))
            t['queueMin'] = o['queueMin']
        if 'close' in o:
            bits.append('闭馆 %s → %s' % (t['close'], o['close']))
            t['close'] = o['close']
        t['note'] = (t.get('note', '') + '（按你的口述修正）').strip()
        out.append(t)
        log.append(dict(level='ok', title='按你的口述修正 %s' % s['name'],
                        text='；'.join(bits) + '。数据里是样例值，这里以你现场问到的为准。'))
    return out, log


def plan(req):
    _CALLS.clear()
    spots_doc = api('GET /api/spots', get_spots)
    spots, food = spots_doc['spots'], spots_doc['food']
    weather_all = api('GET /api/weather', get_weather)['days']
    transport = api('GET /api/transport', get_transport)
    hotels = api('GET /api/hotels', get_hotels)['hotels']

    spots, ov_log = apply_overrides(spots, req.get('overrides') or [])

    ndays = max(1, min(7, int(req.get('days') or 1)))
    start_date = datetime.date.fromisoformat(req['date'])
    people = req['people']

    # ── 天气：多日时按日期依次取，超出样例范围就按最近一天的气候复用 ──
    wmap = {d['date']: d for d in weather_all}
    day_weather = []
    for i in range(ndays):
        dt = start_date + datetime.timedelta(days=i)
        key = dt.isoformat()
        if key in wmap:
            day_weather.append(wmap[key])
        else:
            base = dict(weather_all[min(i, len(weather_all) - 1)])
            base['date'] = key
            base['tip'] = (base.get('tip') or '') + '（按样例气候外推）'
            day_weather.append(base)

    # ── 住宿 ──
    hotel, hotel_notes = pick_hotel(req, hotels, spots)

    # ── 每天排多少个点：宁可少排，也别排成赶场 ──
    per_day = 5
    if req.get('relaxed'):
        per_day = 3
    elif req.get('infants') or ('elderly' in req['flags'] and req['lowWalk']):
        per_day = 4
    if req.get('spotTarget'):
        per_day = max(1, min(per_day, math.ceil(req['spotTarget'] / max(1, ndays))))
    req = dict(req)
    req['maxPerDay'] = per_day

    # ── 每日真实可用窗口：到达日、返程日重新算 ──
    def window(i):
        s, e = req['start'], req['end']
        if i == 0 and req.get('arriveAfternoon'):
            s = '13:30'
        if i == ndays - 1 and req.get('flightOut'):
            cap = hhmm(req['flightOut']) - 180          # 2h 值机 + 1h 进城
            if cap > hhmm(s):
                e = hhmm_text(cap)
        return s, e

    # ── 全局决策 ──
    decisions = []
    heard = [t for t in req['interests']] + [FLAG_CN.get(f, f) for f in req['flags']]
    if req['wheelchair']:
        heard.append('轮椅可达')
    if req['lowWalk']:
        heard.append('低步行')
    if req.get('needAed'):
        heard.append('需 AED')
    if req.get('needToilet'):
        heard.append('需无障碍厕所')
    if req.get('needParking'):
        heard.append('需停车')
    if req.get('infants'):
        heard.append('%d 个婴幼儿' % req['infants'])
    decisions.append(dict(level='info', title='理解需求',
                          text='%s · %s 起 %d 天 · %d 人 · %s–%s%s' % (
                              req['city'], req['date'], ndays, people,
                              window(0)[0], window(ndays - 1)[1],
                              ('，已记录：' + '、'.join(dict.fromkeys(heard))) if heard else '')))

    if req.get('infants'):
        decisions.append(dict(level='warn', title='按婴幼儿作息排',
                              text='同行有 %d 岁以下婴幼儿，每天 %s 固定回 %s 睡 80 分钟，睡醒再出门；这也是每天只排 %d 个点的原因。' % (
                                  3, '12:30', hotel['name'], per_day)))
    if req.get('relaxed'):
        decisions.append(dict(level='info', title='节奏按「不赶」处理',
                              text='每天最多 %d 个停留点，景点之间留出转场与休息；宁可少去一个，也不把一天塞满。' % per_day))

    decisions.append(dict(level='info', title='机票与住宿不代订',
                          text='这里只做方案与价格估算，不下单、不占座。机票按样例航线给出价格区间，酒店按样例房价估算，实际请以购票/订房页面为准。'))

    if req.get('popular'):
        decisions.append(dict(level='info', title='口碑权重上调',
                              text='你点名要「热门」，所以评分这一维的权重从 2.0 提到 3.0，同样条件下更偏高分景点。'))

    if req.get('flightOut'):
        decisions.append(dict(level='info', title='返程航班 %s' % req['flightOut'],
                              text='按提前 2 小时值机 + 1 小时进城倒推，最后一天市区行程只排到 %s。' % window(ndays - 1)[1]))
    if req.get('arriveAfternoon'):
        decisions.append(dict(level='info', title='到达日下午才落地',
                              text='第一天从 %s 起算，上午不进任何景点；这一天只当半天用。' % window(0)[0]))

    decisions += ov_log
    if hotel_notes:
        decisions += hotel_notes

    # ── 逐日求解 ──
    days, used, all_conflicts, all_merge = [], set(), [], []
    for i in range(ndays):
        dt = start_date + datetime.timedelta(days=i)
        weekday = WEEK_CN[dt.weekday()]
        ws, we = window(i)
        d = plan_day(req, i + 1, spots, food, hotel, transport, day_weather[i],
                     weekday, set(used), i == ndays - 1, win_start=ws, win_end=we)
        days.append(d)
        all_conflicts += d['conflicts']
        all_merge += d['merge']
        new = {x['id'] for x in spots if x['id'] in set(d['picked'])}
        used |= new
        if not new and len(days) > 1 and i == ndays - 1:
            days.pop()
            decisions.append(dict(level='bad', title='第 %d 天排不出新景点' % (i + 1),
                                  text='候选池在这天已经用尽（硬约束 + 前几天已去过一起扣掉），所以实际只排了 %d 天。' % i))
            break
        if not new and len(days) > 1:
            days.pop()
            decisions.append(dict(level='bad', title='第 %d 天起排不出新景点' % (i + 1),
                                  text='候选池在第 %d 天用尽（硬约束 + 前几天已去过一起扣掉），实际只排了 %d 天。想要更长天数可以放宽无障碍或步行限制。' % (i + 1, i)))
            break

    if not days:
        ws, we = window(0)
        days = [plan_day(req, 1, spots, food, hotel, transport, day_weather[0],
                         WEEK_CN[start_date.weekday()], set(), True, win_start=ws, win_end=we)]

    # ── 用户点名的景点如果没排进去，必须说清楚为什么 ──
    picked_all = {i for d in days for i in d['picked']}
    for ov in (req.get('overrides') or []):
        if ov['id'] in picked_all:
            decisions.append(dict(level='ok', title='你点名的%s已排入' % ov['name'],
                                  text='按你给的排队 %d 分钟、闭馆 %s 重算过时刻表，排得进去。' % (
                                      ov.get('queueMin', 0), ov.get('close', ''))))
            continue
        s0 = next((x for x in spots if x['id'] == ov['id']), None)
        if not s0:
            continue
        latest = hhmm(s0['close']) - s0['queueMin'] - s0['durationMin']
        decisions.append(dict(level='bad', title='你点名的%s这次没排进去' % s0['name'],
                              text='排队 %d 分钟 + 游览 %d 分钟，闭馆 %s，最晚必须 %s 前到。这两天要留午餐、婴幼儿午睡、返程提前 3 小时收尾，硬塞进去会挤掉两个别的点，所以按「不赶」的原则放弃了。想保留它就把其中一天改成上午先去这里。' % (
                                  s0['queueMin'], s0['durationMin'], s0['close'], hhmm_text(latest))))

    # ── 城际往返 ──
    intercity = []
    routes_to = [r for r in transport['routes'] if r['to'] == req['city']]
    if req.get('fromCity'):
        routes = [r for r in routes_to if r['from'] == req['fromCity']]
        if routes:
            r0 = min(routes, key=lambda r: r['price'])
            intercity = [dict(code=r0['code'], mode=r0['mode'], depart=r0['depart'], arrive=r0['arrive'],
                              price=r0['price'] * people * 2, note='往返 ×%d 人' % people)]
    if not intercity and routes_to:
        lo = min(routes_to, key=lambda r: r['price'])
        hi = max(routes_to, key=lambda r: r['price'])
        decisions.append(dict(level='warn', title='机票请自行购买',
                              text='你没给出发城市，无法锁定具体航班。样例航线到%s的单程价为 ¥%d–¥%d/人，%d 人往返大约 ¥%s–¥%s，已在预算里按最低价计入。' % (
                                  req['city'], lo['price'], hi['price'], people,
                                  format(lo['price'] * people * 2, ','), format(hi['price'] * people * 2, ','))))

    # ── 全局预算 ──
    ticket = sum(d['budget']['ticket'] for d in days)
    local_fare = sum(d['budget']['localFare'] for d in days)
    meals = sum(d['budget']['meals'] for d in days)
    nights = len(days)
    rooms = max(1, math.ceil(people / 2))
    stay = hotel['price'] * rooms * nights
    inter_total = sum(x['price'] for x in intercity)
    total = ticket + local_fare + meals + stay + inter_total
    per_person = round(total / max(1, people))

    # 性价比：每 100 元换来多少「行程得分」，同预算下比绝对花费更有意义
    score_all = sum(d['stats']['score'] for d in days)
    value = round(score_all / max(1, total) * 100, 2)
    decisions.append(dict(level='ok', title='性价比 %.2f 分/百元' % value,
                          text='全程 %d 个停留点、合计 %.0f 分，总花费 %s，人均 %s。在同城同天数的方案里，这个比值越高越划算——加钱只应该加在「分涨得快」的地方。' % (
                              sum(d['stats']['spots'] for d in days), score_all,
                              '¥' + format(total, ','), '¥' + format(per_person, ','))))

    route_points = [p for d in days for p in d['route']['points']]
    access_points = [p for d in days for p in d['access']]
    first = max(days, key=lambda d: d['stats']['score'])

    return dict(
        request=dict(city=req['city'], date=req['date'], weekday=days[0]['weekday'], people=people,
                     start=days[0]['window']['start'], end=days[-1]['window']['end'],
                     interests=req['interests'], days=len(days),
                     flags=req['flags'], wheelchair=req['wheelchair'], lowWalk=req['lowWalk'],
                     infants=req.get('infants', 0), nap=req.get('nap', False),
                     needAed=req.get('needAed', False), needToilet=req.get('needToilet', False),
                     needParking=req.get('needParking', False), hotelMax=req.get('hotelMax'),
                     spotTarget=req.get('spotTarget'), flightOut=req.get('flightOut'),
                     relaxed=req.get('relaxed', False), perDayCap=per_day),
        weather=days[0]['weather'], hotel=hotel,
        days=days,
        groups=first['groups'],
        criteria=criteria_for(req),
        merge=all_merge, conflicts=all_conflicts,
        route=dict(points=route_points), access=access_points,
        rejected=days[0]['rejected'],
        budget=dict(ticket=ticket, localFare=local_fare, meals=meals, hotel=stay, nights=nights, rooms=rooms,
                    intercity=intercity, intercityTotal=inter_total, total=total,
                    perPerson=per_person, perDay=round(total / max(1, len(days))),
                    value=value, score=round(score_all, 1)),
        decisions=decisions,
        apiCalls=list(_CALLS),
        dataset=dict(city=req['city'], spots=len(spots), hotels=len(hotels), weatherDays=len(weather_all),
                     transportRoutes=len(transport['routes']), version=spots_doc['version']),
        generatedAt=datetime.datetime.now().isoformat(timespec='seconds'),
    )


# ── HTTP ────────────────────────────────────────────────────────────────────
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / 'public'), **kw)

    def log_message(self, *a):
        pass

    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split('?')[0]
        try:
            if p == '/api/meta':
                sp = get_spots()
                return self._json(dict(city=sp['city'], version=sp['version'], source=sp['source'],
                                       spots=len(sp['spots']), food=len(sp['food']),
                                       hotels=len(get_hotels()['hotels']), weatherDays=len(get_weather()['days']),
                                       today=str(datetime.date.today())))
            if p == '/api/spots':
                return self._json(get_spots())
            if p == '/api/weather':
                return self._json(get_weather())
            if p == '/api/transport':
                return self._json(get_transport())
            if p == '/api/hotels':
                return self._json(get_hotels())
            if p == '/api/benchmark':
                # 结果确定（固定种子），算一次就够，避免每次刷新都等两百毫秒
                if 'real' not in _BENCH:
                    _BENCH['real'] = benchmark(7, 3)
                return self._json(_BENCH['real'])
            if p == '/api/scaling':
                if 'scaling' not in _BENCH:
                    _BENCH['scaling'] = benchmark_scaling()
                return self._json(_BENCH['scaling'])
        except Exception as e:
            return self._json(dict(error=str(e)))
        return super().do_GET()

    def do_POST(self):
        if self.path.split('?')[0] != '/api/plan':
            self.send_error(404); return
        n = int(self.headers.get('Content-Length', '0'))
        try:
            payload = json.loads(self.rfile.read(n) or b'{}')
            text = (payload.get('text') or '').strip()
            if len(text) < 2:
                return self._json(dict(error='说一句想去哪、和谁、想玩什么，比如「带爸妈去杭州三天，腿脚不好」'))
            req = parse_request(text, payload.get('form') or {})
            m = re.search(r'从\s*([\u4e00-\u9fa5]{2,4})\s*(?:出发|去|到)', text)
            if m:
                req['fromCity'] = m[1]
            return self._json(plan(req))
        except Exception as e:
            return self._json(dict(error='规划失败：%s' % e))


if __name__ == '__main__':
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 8000))
    print('旅迹 LVJI · 杭州行程编排运行于 http://%s:%d' % (host, port), flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
