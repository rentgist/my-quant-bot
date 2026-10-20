from pathlib import Path
import tempfile
import textwrap
import unittest

from streamlit.testing.v1 import AppTest

SOURCE = (Path(__file__).resolve().parents[1] / 'final.py').read_text()


class CalendarGuidanceUITests(unittest.TestCase):
    def test_calendar_page_and_prompt_share_official_events(self):
        with tempfile.TemporaryDirectory() as directory:
            start=SOURCE.index('    st.subheader("📅 마켓 캘린더')
            end=SOURCE.index('    st.markdown("---")',start)
            script=("import streamlit as st\nimport pandas as pd\nimport datetime\nimport calendar_manager\n"
                    f"calendar_manager.CALENDAR_FILE = {str(Path(directory)/'calendar.csv')!r}\n"
                    "calendar_manager.calendar_today=lambda:datetime.date(2026,10,20)\n"+
                    textwrap.dedent(SOURCE[start:end]))
            app=AppTest.from_string(script).run()
            self.assertFalse(app.exception)
            table=app.dataframe[0].value
            self.assertTrue(table.Event.str.contains('FOMC 정책결정').any())
            self.assertTrue(table.Event.str.contains('GOOGL').any())
            self.assertIn('미확인',app.caption[1].value)

    def test_action_panel_does_not_render_a_250_sale_in_panic(self):
        start=SOURCE.index('    with defensive_action_panel:')
        end=SOURCE.index('    with defensive_performance_panel:',start)
        block=textwrap.dedent(SOURCE[start:end])
        script='''import streamlit as st
from regime_playbook import apply_market_safety, build_regime_action_plan
market_regime=apply_market_safety({"status":"ok","code":"CRASH","as_of":"2026-10-20","confidence":72,"indicators":{}},panic_detected=True,provisional=True)
regime_action=build_regime_action_plan(5000,3500,market_regime,account_confirmed=False)
regime_color="#b91c1c"
account_confirmed=False
defensive_action_panel=st.container()
'''+block
        app=AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[3].value,'0원')
        self.assertEqual(app.metric[0].label,'입력 주식 (예시)')
        self.assertIn('장중 잠정 일봉',app.caption[0].value)
        self.assertNotIn('250만원', '\n'.join(x.value for x in app.markdown))
