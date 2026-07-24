import ast
import os
import tempfile
import unittest
from pathlib import Path


def load_regime_classifier():
    signals_path = Path(__file__).resolve().parents[1] / "signals.py"
    module = ast.parse(signals_path.read_text(encoding="utf-8"))
    function_node = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "calculate_regime_classification"
    )
    isolated_module = ast.Module(body=[function_node], type_ignores=[])
    namespace = {}
    exec(compile(isolated_module, str(signals_path), "exec"), namespace)
    return namespace["calculate_regime_classification"]


class RegimeClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classify = staticmethod(load_regime_classifier())

    def classify_in_tempdir(self, macro, flow, above_ma20, warning_days=1):
        previous_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            try:
                return self.classify(
                    macro,
                    flow,
                    above_ma20,
                    warning_days_override=warning_days,
                )
            finally:
                os.chdir(previous_cwd)

    def test_fx_score_alone_cannot_trigger_conditional_go(self):
        regime, action, _ = self.classify_in_tempdir(50, 50, False)

        self.assertIn("경고 국면", regime)
        self.assertNotIn("조건부 GO", regime)
        self.assertIn("20일선 미탈환", action)

    def test_conditional_go_requires_ma20_reclaim(self):
        regime, action, _ = self.classify_in_tempdir(50, 50, True)

        self.assertIn("조건부 GO", regime)
        self.assertIn("20일선 탈환 완료", action)

    def test_strong_go_remains_available_after_ma20_reclaim(self):
        regime, _, _ = self.classify_in_tempdir(80, 80, True)

        self.assertIn("강력 GO", regime)

    def test_flow_recovery_with_weak_macro_stays_in_warning(self):
        regime, action, _ = self.classify_in_tempdir(25, 80, True)

        self.assertIn("경고 국면", regime)
        self.assertNotIn("GO (", regime)
        self.assertIn("매크로 확인이 부족", action)


if __name__ == "__main__":
    unittest.main()
