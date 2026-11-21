import sys, unittest, itertools
sys.path.insert(0, '.')
from server import (parse_request, plan, hhmm, get_spots, build_group, solve_group,
                    objective, eval_order, synth_instance, benchmark,
                    get_weather as get_weather_api, get_transport as get_transport_api,
                    get_hotels as get_hotels_api)


def P(text, form=None):
    req = parse_request(text, form or {})
    return plan(req)


class T(unittest.TestCase):
    def test_parse_people_and_flags(self):
        p = parse_request('带爸妈和孩子去杭州玩一天，腿脚不太方便', {})
        self.assertEqual(p['city'], '杭州')
        self.assertIn('elderly', p['flags'])
        self.assertIn('kids', p['flags'])
        self.assertTrue(p['lowWalk'], '腿脚不方便应触发低步行策略')

    def test_parse_number(self):
        self.assertEqual(parse_request('我们五个人去杭州', {})['people'], 5)
        self.assertEqual(parse_request('三个人', {})['people'], 3)

    def test_parse_interests_and_weather_align(self):
        p = parse_request('明天去杭州看博物馆，下雨也不想淋着', {})
        self.assertIn('博物馆', p['interests'])
        self.assertTrue(p['preferIndoor'])
        self.assertEqual(p['weather']['date'], p['date'])

    def test_plan_single_has_timeline(self):
        r = P('明天去杭州玩一天，想看西湖和老街，两个人')
        g = r['groups'][0]
        self.assertGreaterEqual(g['stats']['spots'], 2)
        self.assertTrue(any(x['type'] == 'meal' for x in g['timeline']))
        self.assertGreater(r['budget']['total'], 0)

    def test_no_time_overlap(self):
        r = P('去杭州一天，想看博物馆和茶园')
        for g in r['groups']:
            spans = [(hhmm(x['start']), hhmm(x['end'])) for x in g['timeline'] if x['type'] in ('spot', 'meal')]
            for a, b in zip(spans, spans[1:]):
                self.assertLessEqual(a[1], b[0] + 1, '时间不应重叠: %s → %s' % (a, b))

    def test_wheelchair_only_accessible(self):
        r = P('带坐轮椅的奶奶去杭州一天，看西湖')
        spots = {s['id']: s for s in get_spots()['spots']}
        for g in r['groups']:
            for x in g['timeline']:
                if x['type'] == 'spot':
                    self.assertTrue(x['access']['wheelchair'], '%s 对轮椅不可达' % x['name'])

    def test_rain_prefers_indoor(self):
        r = P('明天杭州下一天雨，想去逛逛', {})
        spots = {s['id']: s for s in get_spots()['spots']}
        names = {x['name'] for g in r['groups'] for x in g['timeline'] if x['type'] == 'spot'}
        indoor = [n for n in names if any(s['name'] == n and s['indoor'] for s in spots.values())]
        self.assertGreaterEqual(len(indoor), 1, '雨天应至少安排一个室内点，实际: %s' % names)

    def test_split_groups_for_elderly_and_kids(self):
        r = P('带爸妈和两个孩子去杭州玩一天')
        self.assertEqual(len(r['groups']), 2)
        self.assertEqual(r['groups'][0]['id'], 'A')
        self.assertTrue(r['merge'], '分组后应有午餐汇合点')

    def test_spot_inside_open_window(self):
        r = P('去杭州一天，随便逛逛')
        spots = {s['name']: s for s in get_spots()['spots']}
        for g in r['groups']:
            for x in g['timeline']:
                if x['type'] == 'spot':
                    s = spots[x['name']]
                    self.assertGreaterEqual(hhmm(x['start']), hhmm(s['open']))
                    self.assertLessEqual(hhmm(x['end']), hhmm(s['close']))

    def test_api_calls_recorded(self):
        r = P('去杭州一天')
        apis = [c['api'] for c in r['apiCalls']]
        self.assertIn('GET /api/spots', apis)
        self.assertIn('GET /api/weather', apis)
        self.assertIn('GET /api/hotels', apis)
        self.assertIn('GET /api/transport', apis)


class TSolver(unittest.TestCase):
    """最优化外层（贪心构造 + 顺序空间 ILS）与最优性验证。"""

    def test_optimize_attached_and_never_worse(self):
        for text in ('去杭州一天，随便逛逛', '带坐轮椅的奶奶去杭州一天，看西湖', '带爸妈和两个孩子去杭州玩一天'):
            r = P(text)
            for g in r['groups']:
                o = g['optimize']
                self.assertIn('base', o)
                self.assertIn('best', o)
                self.assertIn('trace', o)
                self.assertGreaterEqual(o['best'] + 1e-6, o['base'], 'ILS 结果不应差于构造解')

    def test_objective_matches_score_sum(self):
        r = P('去杭州一天，想看博物馆')
        for g in r['groups']:
            spots = [x for x in g['timeline'] if x['type'] == 'spot']
            self.assertAlmostEqual(objective(g), sum(s['score'] for s in spots), places=2)

    def test_trace_is_monotonic(self):
        r = P('明天去杭州玩一天，想看西湖和博物馆')
        for g in r['groups']:
            trace = [v for _, v in g['optimize']['trace']]
            for a, b in zip(trace, trace[1:]):
                self.assertGreaterEqual(b + 1e-6, a, '收敛轨迹必须单调不减')

    def test_order_mode_respects_priority(self):
        """指定顺序时，第一个可行的点就该被排进去。"""
        req = parse_request('去杭州一天', {})
        doc = get_spots()
        spots, food = doc['spots'], doc['food']
        hotel = get_hotels_api()['hotels'][0]
        weather = get_weather_api()['days'][0]
        transport = get_transport_api()
        pool = [s for s in spots if s['wheelchair']]
        # 把「京杭大运河」放到最前，它应成为当天第一站
        first = next(s for s in pool if '运河' in s['name'])
        order = [first['id']] + [s['id'] for s in pool if s['id'] != first['id']]
        g = build_group(pool, food, hotel, weather, req, transport, 9 * 60, 18 * 60,
                        False, '周五', dict(id='A', name='T', members=1, profile='x'),
                        allow_lunch=False, order=order)
        got = [x['name'] for x in g['timeline'] if x['type'] == 'spot']
        self.assertTrue(got)
        self.assertEqual(got[0], first['name'])

    def test_bruteforce_optimality_on_small_instance(self):
        """6 个点的合成算例上，ILS 应与全排列穷举的最优值一致。"""
        pool = synth_instance(6, seed=11)
        weather = get_weather_api()['days'][0]
        transport = get_transport_api()
        hotel = dict(get_hotels_api()['hotels'][0]); hotel['name'] = '起点'
        crit = dict(city='杭州', date=weather['date'], start='09:00', end='19:00', interests=[],
                    flags=[], wheelchair=False, lowWalk=False, people=1, groupSize=1,
                    preferIndoor=False, weather=weather)
        best = None
        for perm in itertools.permutations(pool):
            ok, v = eval_order(list(perm), hotel, crit, weather, False, transport, 9 * 60, 19 * 60)
            if ok and (best is None or v > best):
                best = v
        self.assertIsNotNone(best, '该算例应存在可行解')
        g = solve_group(pool, [], hotel, weather, crit, transport, 9 * 60, 19 * 60,
                        False, '周五', dict(id='A', name='T', members=1, profile='x'),
                        allow_lunch=False, iters=160, seed=11)
        gap = (best - objective(g)) / abs(best) * 100
        self.assertLess(gap, 2.0, 'gap 应小于 2%%，实际 %.2f%%' % gap)

    def test_benchmark_shape(self):
        r = benchmark(6, 2)
        self.assertTrue(r['trials'], '应至少产出一组有效算例')
        for t in r['trials']:
            self.assertIsNotNone(t['brute']['value'], '穷举最优不能为 None')
            self.assertGreater(t['feasiblePerms'], 0, '必须存在可行排列')
            self.assertGreaterEqual(t['gapPct'], -0.001)


if __name__ == '__main__':
    unittest.main()
