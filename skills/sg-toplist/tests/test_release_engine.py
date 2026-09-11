"""Public release regressions, independent of the frozen Golden cases."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_input import audit_dataset, normalize_payload, parse_interval
from ranking_engine import analyze_periods


def period(index=0, ids=('A', 'B'), **overrides):
    start = index * 7 + 1
    value = dict(period=f'2026-07-{start:02d}~2026-07-{start+6:02d}',
                 platform='天猫', scope='全网', category='餐具', ranking_metric='交易总量',
                 top_n=len(ids), source_file='sample.csv', sheet=f'week-{index}',
                 rows=[dict(product_id=pid, rank=i+1, title='家用陶瓷餐具', shop='甲店')
                       for i, pid in enumerate(ids)])
    value.update(overrides)
    return value


class ReleaseEngineTests(unittest.TestCase):
    def test_blocked_snapshot_has_no_business_outputs(self):
        bad = period()
        bad['rows'][1]['rank'] = 1
        result = analyze_periods([bad])
        self.assertEqual(result['facts'], [])
        self.assertEqual(result['structure']['periods'], [])
        self.assertTrue(all(value is None for value in result['actions'].values()))
        self.assertEqual(result['opportunities'][0]['code'], 'REPAIR_DATA_FIRST')

    def test_good_island_continues_with_original_bad_evidence(self):
        bad = period(category='坏岛')
        bad['rows'][1]['rank'] = 1
        inputs = [bad, period(category='好岛')]
        original = audit_dataset({'periods': inputs})
        result = analyze_periods(inputs, original)
        self.assertEqual(result['audit']['issues'], original['issues'])
        self.assertEqual([x['category'] for x in result['structure']['periods']], ['好岛'])
        self.assertEqual(len(result['analysis_scope']['eligible_islands']), 1)
        self.assertTrue(any(result['actions'].values()))

    def test_bad_middle_period_does_not_bridge_good_periods(self):
        inputs = [period(0), period(1), period(2)]
        inputs[1]['rows'][1]['rank'] = 1
        result = analyze_periods(inputs)
        self.assertEqual(result['trajectories']['summary']['matched_count'], 0)
        self.assertFalse(result['temporality']['strong_trend'])
        self.assertEqual(len(result['structure']['periods']), 2)

    def test_all_fact_and_opportunity_positions_are_structured(self):
        result = analyze_periods([period(), period(1, ids=('B', 'C'))])
        for item in result['facts'] + result['opportunities']:
            position = item['data_position_and_definition']
            self.assertIsInstance(position, (dict, list), item['code'])
            self.assertIn('island_id', str(position), item['code'])
            self.assertIn('file', str(position), item['code'])
            self.assertIn('sheet', str(position), item['code'])

    def test_promotion_cycle_is_not_fixed_seven_days(self):
        result = analyze_periods([period(period='2026-07-01~2026-07-30')])
        cycle = result['actions']['main_promotion']['validation']['cycle']
        self.assertNotIn('7天', cycle)
        self.assertIn('预登记', cycle)

    def test_even_count_interval_midpoint_median(self):
        data = period()
        data['rows'][0]['price'] = 10
        data['rows'][1]['price'] = 30
        value = analyze_periods([data])['structure']['periods'][0]['price_analysis']
        self.assertEqual(value['estimated_midpoint_median'], 20)

    def test_reentry_checks_identity_across_absence(self):
        inputs = [period(0, ('A', 'B')), period(1, ('B', 'C')), period(2, ('A', 'B'))]
        inputs[2]['rows'][0].update(title='智能手机', shop='另一个店')
        result = analyze_periods(inputs)
        self.assertFalse(result['trajectories']['reentries'])
        self.assertTrue(result['trajectories']['reuse_suspects'])

    def test_reentry_history_resets_on_uncomparable_gap(self):
        inputs = [period(0, ('A', 'B')), period(1, ('B', 'C')), period(2, ('B', 'C')), period(3, ('A', 'B'))]
        inputs[2]['rows'][1]['rank'] = 1
        result = analyze_periods(inputs)
        self.assertFalse(result['trajectories']['reentries'])

    def test_reused_id_never_resumes_safe_trajectory(self):
        inputs = [period(0), period(1), period(2)]
        for p in inputs[1:]:
            p['rows'][0].update(title='智能手机', shop='新店')
        result = analyze_periods(inputs)
        self.assertFalse(any(x['safe_for_trajectory'] for x in result['trajectories']['matched'] if x['product_id'] == 'A'))

    def test_different_length_count_intervals_are_not_compared(self):
        inputs = [period(), period(1, period='2026-07-08~2026-07-30')]
        for i, p in enumerate(inputs):
            p['rows'][0]['buyers'] = (i+1)*10
        result = analyze_periods(inputs)
        for match in result['trajectories']['matched']:
            self.assertNotIn('buyers', match['interval_changes'])
        self.assertFalse(result['temporality']['strong_trend'])
        self.assertIn('异长周期', result['temporality']['label'])
        self.assertTrue(all(item['confidence'] == '低' for item in result['opportunities']))

    def test_pollution_id_in_other_platform_does_not_remove_clean_match(self):
        clean = [period(), period(1)]
        bad = period(platform='淘宝')
        bad['rows'][0]['title'] = '福利专拍链接'
        result = analyze_periods(clean + [bad])
        self.assertEqual(result['sensitivity']['all_data']['matched_count'], 2)
        self.assertEqual(result['sensitivity']['cleaned_view']['matched_count'], 2)

    def test_negative_or_reversed_inequality_is_not_valid_metric_interval(self):
        self.assertIsNone(parse_interval('<-1'))
        self.assertIsNone(parse_interval(-10))

    def test_identity_risk_in_other_platform_does_not_flag_clean_trajectory(self):
        clean = [period(), period(1)]
        reused = [period(platform='淘宝'), period(1, platform='淘宝')]
        reused[1]['rows'][0].update(title='手机', shop='另一个店')
        result = analyze_periods(clean + reused, own_product_ids=['A'])
        self.assertEqual(result['severe_error_guards']['product_mismatch'], 0)
        safe = result['structure']['own_product_positioning']['safe_match_count']
        self.assertEqual(safe, 2)

    def test_polluted_link_cannot_supply_strong_trend_evidence(self):
        inputs = []
        for i in range(4):
            p = period(i, ('A', 'B', 'C', 'D'))
            p['rows'][0].update(rank=4-i, title='福利专拍链接', buyers=10*(i+1), visitors=100*(i+1))
            for row, rank in zip(p['rows'][1:], [rank for rank in range(1,5) if rank != 4-i]):
                row['rank'] = rank
            inputs.append(p)
        self.assertFalse(analyze_periods(inputs)['temporality']['strong_trend'])

    def test_duplicate_id_is_unsafe_for_own_positioning(self):
        result = analyze_periods([period(ids=('A', 'A'))], own_product_ids=['A'])
        self.assertEqual(result['structure']['own_product_positioning']['safe_match_count'], 0)

    def test_repeated_normalisation_preserves_rank_raw_and_topn_origin(self):
        raw = period()
        raw.pop('top_n')
        raw['rows'][1]['rank'] = 'bad-rank'
        first = normalize_payload({'periods': [raw]})
        second = normalize_payload(first)
        self.assertEqual(first['periods'][0]['rows'][1]['rank_raw'], second['periods'][0]['rows'][1]['rank_raw'])
        self.assertEqual(second['periods'][0]['top_n_source'], 'max_rank_inferred')


if __name__ == '__main__':
    unittest.main()
