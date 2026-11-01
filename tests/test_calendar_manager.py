import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import calendar_manager as calendar


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.original_today = calendar.calendar_today
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / 'calendar.csv'
        self.patchers = [
            patch.object(calendar, 'CALENDAR_FILE', str(self.file)),
            patch.object(calendar, 'calendar_today', return_value=dt.date(2026, 10, 20)),
        ]
        for p in self.patchers:
            p.start()
            self.addCleanup(p.stop)

    def save(self, rows):
        calendar.save_calendar(pd.DataFrame(rows, columns=calendar.CALENDAR_COLUMNS))

    def test_first_read_contains_official_events_without_creating_csv(self):
        result = calendar.get_upcoming_events_string()
        self.assertIn('2026-10-22 (KST)', result)
        self.assertIn('FOMC 정책결정', result)
        self.assertIn('2026-10-29 (KST)', result)
        self.assertIn('GOOGL', result)
        self.assertIn('MSFT', result)
        self.assertFalse(self.file.exists())

    def test_earnings_and_fed_are_on_korean_next_day(self):
        df = calendar.load_effective_calendar()
        events = df[df.Event.str.contains('GOOGL|MSFT|10월 FOMC 정책결정')]
        self.assertEqual(set(events.Date), {dt.date(2026, 10, 29)})

    def test_effective_read_preserves_manual_bytes_and_deduplicates(self):
        official = calendar.VERIFIED_EVENTS[0]
        self.save([(*official[:4], '내가 작성한 설명')])
        before = self.file.read_bytes()
        df = calendar.load_effective_calendar()
        self.assertEqual(self.file.read_bytes(), before)
        self.assertEqual(len(df[df.Event.eq(official[2]) & df.Date.eq(dt.date(2026,10,22))]), 1)
        self.assertIn('내가 작성한 설명', df.Notes.tolist())

    def test_sync_is_idempotent_and_preserves_manual_rows(self):
        self.save([('2026-11-26','국내','한국은행 통화정책방향 결정회의','High','내 메모')])
        calendar.sync_core_macro_events()
        calendar.sync_core_macro_events()
        df = calendar.load_calendar()
        self.assertFalse(df.duplicated(['Date','Event']).any())
        self.assertIn('내 메모', df.Notes.tolist())

    def test_expired_or_empty_window_does_not_claim_no_actual_events(self):
        with patch.object(calendar, 'calendar_today', return_value=dt.date(2027,1,20)):
            text = calendar.get_upcoming_events_string()
        self.assertIn('실제 주요 일정이 없다는 뜻이 아닙니다', text)
        self.assertIn('일정 재확인 필요', text)

    def test_metadata_warns_even_with_future_rows(self):
        self.assertIn('일정 재확인 필요', calendar.calendar_coverage_message(dt.date(2026,11,21)))
        self.assertIn('모든 기업·경제', calendar.calendar_coverage_message(dt.date(2026,10,20)))

    def test_corrupt_file_is_not_no_events_or_overwritten(self):
        self.file.write_text('garbled\nvalue\n')
        self.assertIn('일정 확인 실패', calendar.get_upcoming_events_string())
        self.assertEqual(self.file.read_text(), 'garbled\nvalue\n')

    def test_kst_midnight_uses_korean_calendar_date(self):
        class Clock(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026,10,19,16,0,tzinfo=dt.timezone.utc).astimezone(tz)
        # 원래 함수를 사용하여 UTC 다음 날인 한국 날짜를 확인한다.
        with patch.object(calendar.datetime, 'datetime', Clock):
            self.assertEqual(self.original_today(), dt.date(2026,10,20))

    def test_yahoo_ambiguous_window_is_estimate(self):
        ticker = Mock(calendar={'Earnings Date':[dt.date(2026,10,28),dt.date(2026,10,30)]})
        with patch.object(calendar.yf, 'Ticker', return_value=ticker):
            result = calendar.fetch_single_earnings('AVGO','AVGO')
        self.assertIn('2026-10-28 ~ 2026-10-30',result['Notes'])
        self.assertTrue(result['Notes'].startswith('[예상·미확인]'))
        self.assertIn('시간대', result['Notes'])

    def test_partial_failure_does_not_delete_other_ticker_or_manual_history(self):
        self.save([
            ('2026-10-28','실적','NVDA 실적발표','High','자동 업데이트됨'),
            ('2026-10-26','실적','AVGO 실적발표','High','자동 업데이트됨'),
            ('2026-07-10','실적','AVGO 실적발표','High','자동 업데이트됨'),
            ('2026-10-28','실적','AVGO 실적발표','High','수동 메모'),
        ])
        def fetch(name, ticker):
            if name == 'AVGO':
                return dict(Date='2026-10-29',Type='실적',Event='AVGO 실적발표',Impact='High',Notes='[예상·미확인] 새 예상')
            return None
        with patch.object(calendar,'fetch_single_earnings',side_effect=fetch):
            self.assertTrue(calendar.update_earnings_automatically())
        df=calendar.load_calendar()
        self.assertEqual(len(df),4)
        self.assertIn('NVDA 실적발표', df.Event.tolist())
        self.assertIn('수동 메모', df.Notes.tolist())
        self.assertIn(dt.date(2026,7,10), df.Date.tolist())

    def test_yahoo_cannot_replace_official_earnings(self):
        with patch.object(calendar,'fetch_single_earnings',return_value=dict(
            Date='2026-10-28',Type='실적',Event='MSFT 실적발표',Impact='High',Notes='[예상·미확인] Yahoo')):
            calendar.update_earnings_automatically()
        df=calendar.load_effective_calendar()
        self.assertEqual(len(df[df.Event.str.startswith('MSFT')]),1)
        self.assertEqual(df[df.Event.str.startswith('MSFT')].iloc[0].Date, dt.date(2026,10,29))

    def test_no_earnings_response_preserves_file_bytes(self):
        self.save([('2026-10-28','실적','NVDA 실적발표','High','자동 업데이트됨')])
        before=self.file.read_bytes()
        with patch.object(calendar,'fetch_single_earnings',return_value=None):
            self.assertFalse(calendar.update_earnings_automatically())
        self.assertEqual(before,self.file.read_bytes())

    def test_news_never_infers_missing_year_or_month(self):
        titles=['CPI 3일 발표','CPI 10월 28일 발표','CPI 2025년 10월 28일 발표',
                'CPI 2026년 10월 29일 발표']
        news=Path(self.tmp.name)/'news.json'
        news.write_text(json.dumps([{'title':t} for t in titles]))
        original_join=calendar.os.path.join
        def join(*args):
            return str(news) if args==('data','news_archive.json') else original_join(*args)
        with patch.object(calendar.os.path,'join',side_effect=join):
            self.assertTrue(calendar.update_macro_events_automatically())
        df=calendar.load_calendar()
        self.assertEqual(len(df),1)
        self.assertTrue(df.iloc[0].Notes.startswith('[뉴스 후보·미확인]'))

    def test_existing_yahoo_date_is_superseded_by_official_kst_date_on_read(self):
        self.save([
            ('2026-10-28','실적','MSFT 실적발표','High','자동 업데이트됨'),
            ('2026-07-30','실적','MSFT 실적발표','High','자동 업데이트됨'),
            ('2026-10-28','실적','MSFT 실적발표','High','수동 메모'),
        ])
        before=self.file.read_bytes()
        df=calendar.load_effective_calendar()
        self.assertEqual(self.file.read_bytes(),before)
        old=df[df.Event.eq('MSFT 실적발표') & df.Date.eq(dt.date(2026,10,28))]
        self.assertEqual(old.Notes.tolist(),['수동 메모'])
        self.assertIn(dt.date(2026,7,30),df.Date.tolist())
        self.assertEqual(len(df[df.Event.str.startswith('MSFT') & df.Notes.str.startswith('[공식 확인]')]),1)
        text=calendar.get_upcoming_events_string()
        self.assertNotIn('자동 업데이트됨',text)
        self.assertIn('2026-10-29 (KST) [실적 / 공식 확인] MSFT',text)
