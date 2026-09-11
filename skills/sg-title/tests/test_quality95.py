from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from title_guard import validate_title


def request() -> dict:
    return {'platform': 'jd', 'title': '黑色蓝牙音箱M1',
            'title_core_terms': ['黑色', '蓝牙音箱', 'M1'],
            'keyword_sources': [{'term': term, 'status': 'confirmed', 'source': '用户商品事实'}
                                for term in ['黑色', '蓝牙音箱', 'M1']]}


class RequiredInputTests(unittest.TestCase):
    def test_missing_provenance_cannot_pass(self) -> None:
        for data in ({'platform': 'jd', 'title': '音箱'},
                     {'platform': 'jd', 'title': '音箱', 'title_core_terms': [], 'keyword_sources': []}):
            with self.subTest(data=data):
                self.assertFalse(validate_title(data)['allowed'])

    def test_wrong_input_types_return_errors_not_tracebacks(self) -> None:
        for value in (None, [], 'title', 3):
            with self.subTest(value=value):
                self.assertFalse(validate_title(value)['allowed'])
        for field, value in [('title_core_terms', '音箱'), ('keyword_sources', {}),
                             ('current_requirements', []), ('required_terms', 'M1'),
                             ('preference_profiles', [None])]:
            data = request()
            data[field] = value
            with self.subTest(field=field):
                self.assertFalse(validate_title(data)['allowed'])

    def test_ordinary_facts_still_pass(self) -> None:
        self.assertTrue(validate_title(request())['allowed'])

    def test_undeclared_high_risk_phrase_is_blocked(self) -> None:
        for phrase in ('医疗级', '官方授权', '全网第一', '100%遮光', '迪士尼联名'):
            data = request()
            data['title'] += phrase
            with self.subTest(phrase=phrase):
                self.assertFalse(validate_title(data)['allowed'])

    def test_high_risk_word_requires_evidence_not_just_confirmed_label(self) -> None:
        data = request()
        data['title'] += '官方授权'
        data['title_core_terms'].append('官方授权')
        data['keyword_sources'].append({'term': '官方授权', 'status': 'confirmed', 'source': '热词'})
        self.assertFalse(validate_title(data)['allowed'])

    def test_legitimate_authorization_can_be_supplied(self) -> None:
        data = request()
        data['title'] += '官方授权'
        data['title_core_terms'].append('官方授权')
        data['keyword_sources'].append({'term': '官方授权', 'status': 'confirmed',
                                       'source': '用户提供的本SKU授权书',
                                       'evidence': {'type': 'authorization', 'reference': '授权书第1页',
                                                    'product_match': True}})
        self.assertTrue(validate_title(data)['allowed'])

    def test_user_forbid_blocks_all_unicode_whitespace(self) -> None:
        for space in (' ', '\t', '\n', '\u3000', '\u00a0'):
            data = request()
            data['title'] = '黑色' + space + '蓝牙音箱M1'
            data['current_requirements'] = {'space_policy': 'forbid'}
            with self.subTest(space=repr(space)):
                result = validate_title(data)
                self.assertFalse(result['allowed'])
                self.assertIn('space_forbidden', [x['code'] for x in result['errors']])

    def test_platform_hard_rule_takes_priority_over_user_allow(self) -> None:
        from title_guard import load_profiles
        profiles = load_profiles()
        profiles['platforms']['jd']['space_policy'] = {'value': 'forbid', 'enforcement': 'hard'}
        # 平台规则的控制优先级单独测试；来源有效性由档案测试覆盖。
        profiles['platforms']['jd'].pop('freshness', None)
        data = request()
        data['title'] = '黑色 蓝牙音箱M1'
        data['current_requirements'] = {'space_policy': 'allow'}
        self.assertFalse(validate_title(data, profiles)['allowed'])


class LazyRuleTests(unittest.TestCase):
    def test_day_29_fresh_day_30_due_and_hard_rule_deactivated(self) -> None:
        from platform_guard import inspect_platform
        profile = {
            'version': '1', 'scope': '商品标题', 'status': 'verified',
            'freshness': {'verified_at': '2026-08-01', 'review_after': '2026-08-31', 'interval_days': 30},
            'sources': [{'uri': 'https://helpcenter.jd.com/example', 'status': 'official_verified',
                         'accessed_at': '2026-08-01', 'effective_date': '2026-08-01', 'claim': '测试中的已核实规则'}],
            'length': {'metric': 'codepoints', 'min': 1, 'max': 20, 'enforcement': 'hard'},
            'space_policy': {'value': 'forbid', 'enforcement': 'hard'},
            'symbol_policy': {'forbidden': [], 'enforcement': 'unknown'},
            'max_term_repetitions': {'value': 1, 'enforcement': 'advisory'}}
        source = {'platforms': {'jd': profile}}
        original = copy.deepcopy(source)
        self.assertFalse(inspect_platform(source, 'jd', '2026-08-30')['review_due'])
        for day in ('2026-08-31', '2026-09-01'):
            result = inspect_platform(source, 'jd', day)
            self.assertTrue(result['review_due'])
            self.assertEqual('unknown', result['profile']['length']['enforcement'])
        self.assertEqual(original, source)

    def test_invalid_dates_and_interval_cannot_claim_fresh(self) -> None:
        from platform_guard import inspect_platform
        from title_guard import load_profiles
        source = load_profiles()
        for update in ({'verified_at': '2099-01-01'}, {'review_after': 'garbage'}, {'interval_days': 300}):
            changed = copy.deepcopy(source)
            changed['platforms']['jd']['freshness'].update(update)
            result = inspect_platform(changed, 'jd', '2026-09-07')
            self.assertFalse(result['schema_valid'])

    def test_other_platform_invalid_data_does_not_pollute_selection(self) -> None:
        from platform_guard import inspect_platform
        from title_guard import load_profiles
        source = load_profiles()
        source['platforms']['douyin'] = {'invalid': True}
        result = inspect_platform(source, 'jd', '2026-09-07')
        self.assertTrue(result['schema_valid'])
        self.assertEqual('jd', result['platform'])
        self.assertNotIn('douyin', result['profile'])


class MixedRouteTests(unittest.TestCase):
    def test_mixed_title_and_advertising_preserves_both(self) -> None:
        from title_guard import route_request
        result = route_request('优化商品标题，同时诊断广告投放ROI')
        self.assertTrue(result['title_task'])
        self.assertIn('sg-tmads-report', result['adjacent_routes'])

    def test_pure_advertising_has_no_title_task(self) -> None:
        from title_guard import route_request
        self.assertFalse(route_request('诊断广告投放ROI')['title_task'])

    def test_content_title_does_not_activate_product_title(self) -> None:
        from title_guard import route_request
        self.assertFalse(route_request('写公众号文章标题')['title_task'])


if __name__ == '__main__':
    unittest.main()
