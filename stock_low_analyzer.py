from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Sequence


DAYS_PER_MONTH = 365.2425 / 12


@dataclass(frozen=True)
class Security:
    ticker: str
    listing_date: date
    offer_price: float | None = None
    name: str = ""
    market: str = ""
    currency: str = ""


@dataclass(frozen=True)
class PriceRow:
    day: date
    low: float


@dataclass(frozen=True)
class AnalysisRow:
    ticker: str
    name: str
    market: str
    currency: str
    listing_date: date
    first_price_date: date
    last_price_date: date
    lowest_date: date
    lowest_price: float
    months_to_low: float
    calendar_month_to_low: int
    offer_price: float | None
    low_offer_ratio: float | None
    observations: int


def parse_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"日付形式が不正です: {value!r}")


def parse_optional_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    result = float(value.replace(",", "").strip())
    if not math.isfinite(result) or result <= 0:
        raise ValueError("価格は0より大きい有限値である必要があります")
    return result


def load_securities(path: Path) -> list[Security]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"ticker", "listing_date"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"銘柄CSVに列が不足しています: {', '.join(sorted(missing))}")

        securities: list[Security] = []
        seen: set[str] = set()
        for line_no, row in enumerate(reader, start=2):
            try:
                ticker = (row.get("ticker") or "").strip()
                if not ticker:
                    raise ValueError("tickerが空です")
                if ticker in seen:
                    raise ValueError(f"tickerが重複しています: {ticker}")
                security = Security(
                    ticker=ticker,
                    listing_date=parse_date(row["listing_date"]),
                    offer_price=parse_optional_float(row.get("offer_price")),
                    name=(row.get("name") or "").strip(),
                    market=(row.get("market") or "").strip(),
                    currency=(row.get("currency") or "").strip(),
                )
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{path} の {line_no} 行目: {exc}") from exc
            seen.add(ticker)
            securities.append(security)
    return securities


def _find_column(fieldnames: Sequence[str], candidates: Sequence[str]) -> str | None:
    normalized = {name.strip().lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]
    return None


def load_price_csv(path: Path, listing_date: date) -> list[PriceRow]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        date_col = _find_column(fieldnames, ("Date", "date", "日付"))
        low_col = _find_column(fieldnames, ("Low", "low", "安値"))
        if not date_col or not low_col:
            raise ValueError(f"{path}: Date と Low の列が必要です")

        prices: list[PriceRow] = []
        for line_no, row in enumerate(reader, start=2):
            try:
                day = parse_date(row[date_col].split(" ")[0])
                raw_low = (row.get(low_col) or "").replace(",", "").strip()
                if not raw_low:
                    continue
                low = float(raw_low)
                if day >= listing_date and math.isfinite(low) and low > 0:
                    prices.append(PriceRow(day=day, low=low))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{path} の {line_no} 行目: {exc}") from exc
    prices.sort(key=lambda item: item.day)
    return prices


def months_between(start: date, end: date) -> float:
    return (end - start).days / DAYS_PER_MONTH


def calendar_month_index(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def analyze_security(security: Security, prices: Sequence[PriceRow]) -> AnalysisRow:
    if not prices:
        raise ValueError("上場日以降の有効な株価がありません")
    lowest = min(prices, key=lambda item: (item.low, item.day))
    ratio = lowest.low / security.offer_price if security.offer_price else None
    return AnalysisRow(
        ticker=security.ticker,
        name=security.name,
        market=security.market,
        currency=security.currency,
        listing_date=security.listing_date,
        first_price_date=prices[0].day,
        last_price_date=prices[-1].day,
        lowest_date=lowest.day,
        lowest_price=lowest.low,
        months_to_low=months_between(security.listing_date, lowest.day),
        calendar_month_to_low=calendar_month_index(security.listing_date, lowest.day),
        offer_price=security.offer_price,
        low_offer_ratio=ratio,
        observations=len(prices),
    )


def safe_filename(ticker: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in ticker)


def download_yfinance(securities: Sequence[Security], price_dir: Path) -> list[tuple[str, str]]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "yfinanceが未導入です。`python -m pip install -r requirements.txt` を実行してください"
        ) from exc

    price_dir.mkdir(parents=True, exist_ok=True)
    failures: list[tuple[str, str]] = []
    for security in securities:
        try:
            data = yf.download(
                security.ticker,
                start=security.listing_date.isoformat(),
                progress=False,
                auto_adjust=False,
                actions=True,
                group_by="column",
                threads=False,
            )
            if data.empty:
                raise ValueError("株価データが0件でした")
            if getattr(data.columns, "nlevels", 1) > 1:
                data.columns = data.columns.get_level_values(0)
            output = price_dir / f"{safe_filename(security.ticker)}.csv"
            data.to_csv(output, index_label="Date")
        except Exception as exc:  # 銘柄単位で継続するため
            failures.append((security.ticker, str(exc)))
    return failures


def analyze_all(
    securities: Sequence[Security], price_dir: Path
) -> tuple[list[AnalysisRow], list[tuple[str, str]]]:
    results: list[AnalysisRow] = []
    failures: list[tuple[str, str]] = []
    for security in securities:
        path = price_dir / f"{safe_filename(security.ticker)}.csv"
        try:
            if not path.exists():
                raise FileNotFoundError(f"株価CSVがありません: {path}")
            prices = load_price_csv(path, security.listing_date)
            results.append(analyze_security(security, prices))
        except Exception as exc:
            failures.append((security.ticker, str(exc)))
    return results, failures


RESULT_FIELDS = [
    "ticker",
    "name",
    "market",
    "currency",
    "listing_date",
    "first_price_date",
    "last_price_date",
    "lowest_date",
    "lowest_price",
    "months_to_low",
    "calendar_month_to_low",
    "offer_price",
    "low_offer_ratio",
    "observations",
]


def write_results(path: Path, rows: Sequence[AnalysisRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "ticker": row.ticker,
                    "name": row.name,
                    "market": row.market,
                    "currency": row.currency,
                    "listing_date": row.listing_date.isoformat(),
                    "first_price_date": row.first_price_date.isoformat(),
                    "last_price_date": row.last_price_date.isoformat(),
                    "lowest_date": row.lowest_date.isoformat(),
                    "lowest_price": f"{row.lowest_price:.8g}",
                    "months_to_low": f"{row.months_to_low:.6f}",
                    "calendar_month_to_low": row.calendar_month_to_low,
                    "offer_price": "" if row.offer_price is None else f"{row.offer_price:.8g}",
                    "low_offer_ratio": (
                        "" if row.low_offer_ratio is None else f"{row.low_offer_ratio:.8f}"
                    ),
                    "observations": row.observations,
                }
            )


def _summary(values: Iterable[float]) -> tuple[int, float | None, float | None]:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return 0, None, None
    return len(clean), statistics.mean(clean), statistics.median(clean)


def build_summary(rows: Sequence[AnalysisRow]) -> list[dict[str, str | int]]:
    month_count, month_mean, month_median = _summary(row.months_to_low for row in rows)
    ratio_count, ratio_mean, ratio_median = _summary(
        row.low_offer_ratio for row in rows if row.low_offer_ratio is not None
    )
    return [
        {
            "metric": "months_to_low",
            "unit": "months",
            "count": month_count,
            "mean": "" if month_mean is None else f"{month_mean:.6f}",
            "median": "" if month_median is None else f"{month_median:.6f}",
        },
        {
            "metric": "low_offer_ratio",
            "unit": "ratio",
            "count": ratio_count,
            "mean": "" if ratio_mean is None else f"{ratio_mean:.8f}",
            "median": "" if ratio_median is None else f"{ratio_median:.8f}",
        },
    ]


def write_summary(path: Path, rows: Sequence[AnalysisRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("metric", "unit", "count", "mean", "median"))
        writer.writeheader()
        writer.writerows(build_summary(rows))


def write_failures(path: Path, failures: Sequence[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("ticker", "error"))
        writer.writerows(failures)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="上場日から史上最安値までの月数と、公開価格に対する比率を集計します"
    )
    parser.add_argument("--securities", type=Path, required=True, help="銘柄マスターCSV")
    parser.add_argument("--price-dir", type=Path, default=Path("prices"), help="株価CSVフォルダ")
    parser.add_argument("--output", type=Path, default=Path("results.csv"), help="銘柄別結果CSV")
    parser.add_argument(
        "--summary-output", type=Path, default=Path("summary.csv"), help="統計サマリーCSV"
    )
    parser.add_argument(
        "--failures-output", type=Path, default=Path("failures.csv"), help="失敗銘柄CSV"
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="分析前にYahoo Financeから株価CSVを取得する",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        securities = load_securities(args.securities)
        failures: list[tuple[str, str]] = []
        if args.download:
            failures.extend(download_yfinance(securities, args.price_dir))
        rows, analysis_failures = analyze_all(securities, args.price_dir)
        failures.extend(analysis_failures)
        write_results(args.output, rows)
        write_summary(args.summary_output, rows)
        write_failures(args.failures_output, failures)
        print(f"分析成功: {len(rows)} 銘柄")
        print(f"分析失敗: {len(failures)} 件")
        print(f"結果: {args.output}")
        print(f"統計: {args.summary_output}")
        if failures:
            print(f"失敗一覧: {args.failures_output}")
        return 0 if rows else 2
    except Exception as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
