import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import portfolio_manager


class PortfolioLogTests(unittest.TestCase):
    def test_reads_the_most_recent_dated_snapshot(self):
        with TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            (log_dir / "portfolio_log_20260805.md").write_text(
                "### 해외 계좌 (USD)\n| 종목명 | 비중 | 수량 | 평단가 | 비고 |\n|:---|---:|---:|---:|:---|\n| 이전 (OLD) | 10% | 1 | 1 | - |\n\n---",
                encoding="utf-8",
            )
            (log_dir / "portfolio_log_20260806.md").write_text(
                "### 해외 계좌 (USD)\n| 종목명 | 비중 | 수량 | 평단가 | 비고 |\n|:---|---:|---:|---:|:---|\n| 최신 (NEW) | 10% | 2 | 2 | - |\n\n---",
                encoding="utf-8",
            )

            with patch.object(portfolio_manager, "PORTFOLIO_LOG_DIR", log_dir):
                holdings = portfolio_manager.parse_portfolio_log()

        self.assertEqual(holdings["us"], ["NEW"])


if __name__ == "__main__":
    unittest.main()
