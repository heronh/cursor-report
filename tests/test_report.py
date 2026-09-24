"""Testes unitários para o pipeline de relatório usando unittest."""

import csv
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from report.generate_report import (
    build_activity_csv_rows,
    generate_report,
    write_activity_csv,
    write_repo_report,
)


class TestReportPipeline(unittest.TestCase):
    def test_build_activity_csv_rows_and_write(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            start = date(2026, 9, 1)
            end = date(2026, 9, 3)
            month_start_date = date(2026, 9, 1)
            daily_spend = {
                date(2026, 9, 1): 2.50,
                date(2026, 9, 2): 4.10,
            }
            daily_tokens = {
                date(2026, 9, 1): 15000,
                date(2026, 9, 2): 30000,
            }
            rows = build_activity_csv_rows(
                daily_spend=daily_spend,
                daily_tokens=daily_tokens,
                start=start,
                end=end,
                month_start_date=month_start_date,
                month_total=6.60,
                month_tokens=45000,
                contracted_limit=100.0,
            )

            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["data"], "2026-09-01")
            self.assertEqual(rows[0]["gasto_diario_usd"], 2.5)
            self.assertEqual(rows[0]["tokens_diario"], 15000)
            self.assertEqual(rows[0]["mes_corrente"], "2026-09")
            self.assertEqual(rows[0]["total_mes_corrente_usd"], 6.60)
            self.assertEqual(rows[0]["tokens_mes_corrente"], 45000)
            self.assertEqual(rows[0]["limite_contratado_usd"], 100.0)

            # 2026-09-03 has no spend/tokens recorded, should default to 0
            self.assertEqual(rows[2]["data"], "2026-09-03")
            self.assertEqual(rows[2]["gasto_diario_usd"], 0.0)
            self.assertEqual(rows[2]["tokens_diario"], 0)

            csv_file = tmp_path / "cursor_activity.csv"
            write_activity_csv(rows, csv_file)

            self.assertTrue(csv_file.exists())
            with csv_file.open(newline="", encoding="utf-8") as f:
                reader = list(csv.DictReader(f))
                self.assertEqual(len(reader), 3)
                self.assertEqual(reader[0]["data"], "2026-09-01")
                self.assertEqual(float(reader[0]["gasto_diario_usd"]), 2.5)
                self.assertEqual(int(reader[0]["tokens_diario"]), 15000)
                self.assertEqual(reader[0]["mes_corrente"], "2026-09")
                self.assertEqual(float(reader[0]["total_mes_corrente_usd"]), 6.6)
                self.assertEqual(int(reader[0]["tokens_mes_corrente"]), 45000)
                self.assertEqual(float(reader[0]["limite_contratado_usd"]), 100.0)

    def test_write_repo_report_copies_csv(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            reports_dir = tmp_path / "reports"
            with patch("report.generate_report.REPORTS_DIR", reports_dir):
                report_date = date(2026, 9, 24)
                summary = {"status": "ok"}
                chart_file = tmp_path / "chart.png"
                chart_file.write_text("fake image content")
                charts = {"chart.png": chart_file}
                csv_rows = [
                    {
                        "data": "2026-09-24",
                        "gasto_diario_usd": 1.25,
                        "tokens_diario": 5000,
                        "mes_corrente": "2026-09",
                        "total_mes_corrente_usd": 10.0,
                        "tokens_mes_corrente": 20000,
                        "limite_contratado_usd": 50.0,
                    }
                ]

                write_repo_report(
                    report_date=report_date,
                    summary=summary,
                    charts=charts,
                    markdown="# Report",
                    activity_csv_rows=csv_rows,
                )

                self.assertTrue((reports_dir / "latest" / "cursor_activity.csv").exists())
                self.assertTrue((reports_dir / "2026-09-24" / "cursor_activity.csv").exists())
                self.assertTrue((reports_dir / "latest" / "report.md").exists())
                self.assertTrue((reports_dir / "latest" / "summary.json").exists())

    def test_generate_report_end_to_end_mocked(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_dir = tmp_path / "output"
            reports_dir = tmp_path / "reports"

            mock_client = MagicMock()
            mock_client.fetch_usage_events.return_value = [
                {
                    "timestamp": 1789430400000,
                    "chargedCents": 350,
                    "tokenUsage": {
                        "inputTokens": 1000,
                        "outputTokens": 500,
                        "cacheWriteTokens": 100,
                        "cacheReadTokens": 200,
                    },
                }
            ]
            mock_client.fetch_team_spend.return_value = {
                "members": [{"effectivePerUserLimitDollars": 50.0}],
                "totalMembers": 1,
            }

            with (
                patch("report.generate_report.OUTPUT_DIR", output_dir),
                patch("report.generate_report.REPORTS_DIR", reports_dir),
                patch("report.generate_report.CursorClient", return_value=mock_client),
            ):
                result = generate_report(send_email=False)

                self.assertTrue((output_dir / "cursor_activity.csv").exists())
                self.assertTrue((output_dir / "daily_value.png").exists())
                self.assertTrue((output_dir / "daily_tokens.png").exists())
                self.assertTrue((output_dir / "monthly_limit.png").exists())
                self.assertTrue((reports_dir / "latest" / "cursor_activity.csv").exists())
                self.assertEqual(result["activity_csv"], "cursor_activity.csv")


if __name__ == "__main__":
    unittest.main()
