import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stock_low_analyzer import (  # noqa: E402
    PriceRow,
    Security,
    analyze_security,
    build_summary,
    load_price_csv,
    months_between,
)


class StockLowAnalyzerTests(unittest.TestCase):
    def test_lowest_price_and_ratio(self):
        security = Security("TEST", date(2020, 1, 15), 100.0)
        prices = [
            PriceRow(date(2020, 1, 15), 95.0),
            PriceRow(date(2020, 2, 15), 70.0),
            PriceRow(date(2020, 3, 15), 70.0),
        ]
        row = analyze_security(security, prices)
        self.assertEqual(row.lowest_date, date(2020, 2, 15))
        self.assertEqual(row.lowest_price, 70.0)
        self.assertEqual(row.low_offer_ratio, 0.7)
        self.assertEqual(row.calendar_month_to_low, 1)
        self.assertAlmostEqual(row.months_to_low, months_between(date(2020, 1, 15), date(2020, 2, 15)))

    def test_summary(self):
        rows = [
            analyze_security(
                Security("A", date(2020, 1, 1), 100),
                [PriceRow(date(2020, 1, 1), 50)],
            ),
            analyze_security(
                Security("B", date(2020, 1, 1), 100),
                [PriceRow(date(2020, 3, 1), 75)],
            ),
        ]
        summary = build_summary(rows)
        self.assertEqual(summary[0]["count"], 2)
        self.assertEqual(summary[1]["mean"], "0.62500000")
        self.assertEqual(summary[1]["median"], "0.62500000")

    def test_load_price_csv_ignores_pre_listing_and_invalid_low(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "price.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Date", "Low"])
                writer.writerow(["2019-12-31", "1"])
                writer.writerow(["2020-01-01", ""])
                writer.writerow(["2020-01-02", "10"])
            rows = load_price_csv(path, date(2020, 1, 1))
            self.assertEqual(rows, [PriceRow(date(2020, 1, 2), 10.0)])


if __name__ == "__main__":
    unittest.main()
