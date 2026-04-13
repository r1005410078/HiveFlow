#!/usr/bin/env python3
"""
探测当前环境下 AKShare 可用的 A 股日 K 历史数据源（多接口对比）。

背景：项目主源为腾讯 HTTP（见 tencent_quote_adapter）；AKShare 侧另有东财 / 腾讯等封装。
若腾讯接口长区间受限，可用本脚本快速对比哪些 AK 函数能拉满约一个月的日线。

用法（需在 quant 目录、已 uv sync）::

    cd quant && uv run python scripts/probe_akshare_hist_sources.py

可选环境变量：
  PROBE_SYMBOL   默认 600519（贵州茅台，东财用 6 位码）
  PROBE_DAYS     默认 35（自然日窗口，覆盖约一个月交易日）
"""

from __future__ import annotations

import argparse
import re
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


def _ensure_quant_src_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


@dataclass
class ProbeResult:
    name: str
    ok: bool
    rows: int = 0
    columns: tuple[str, ...] = ()
    error: str = ""
    note: str = ""


def _date_windows(days: int) -> tuple[str, str, str, str]:
    """返回 (ymd_start, ymd_end, dash_start, dash_end)。"""
    end = datetime.now().date()
    start = end - timedelta(days=days)
    ymd_start = start.strftime("%Y%m%d")
    ymd_end = end.strftime("%Y%m%d")
    dash_start = start.strftime("%Y-%m-%d")
    dash_end = end.strftime("%Y-%m-%d")
    return ymd_start, ymd_end, dash_start, dash_end


def _row_count(df) -> int:
    if df is None:
        return 0
    try:
        return int(len(df.index))
    except Exception:
        return 0


def _columns(df) -> tuple[str, ...]:
    if df is None:
        return ()
    try:
        return tuple(str(c) for c in df.columns)
    except Exception:
        return ()


def _list_akshare_hist_candidates(ak) -> list[str]:
    """从 dir(ak) 中找出可能与 A 股历史 K 线相关的符号。"""
    pat = re.compile(
        r"^stock_zh_a_(hist|daily)|^stock_zh_a_hist_",
        re.IGNORECASE,
    )
    names = []
    for n in dir(ak):
        if pat.search(n) and callable(getattr(ak, n, None)):
            names.append(n)
    return sorted(names)


def run_probes(
    *,
    symbol_em: str,
    symbol_tx: str,
    symbol_sina: str,
    ymd_start: str,
    ymd_end: str,
    dash_start: str,
    dash_end: str,
    timeout: float | None,
) -> list[ProbeResult]:
    import akshare as ak

    from interfaces.adapters.market_data.no_http_proxy_env import disabled_http_proxy_env

    results: list[ProbeResult] = []

    def run_one(name: str, fn: Callable, **kwargs) -> None:
        try:
            with disabled_http_proxy_env():
                df = fn(**kwargs)
            n = _row_count(df)
            results.append(
                ProbeResult(
                    name=name,
                    ok=n > 0,
                    rows=n,
                    columns=_columns(df),
                    note="" if n > 0 else "empty dataframe",
                )
            )
        except Exception as exc:
            results.append(
                ProbeResult(
                    name=name,
                    ok=False,
                    error=f"{type(exc).__name__}: {exc}",
                    note=traceback.format_exc(limit=2),
                )
            )

    # 1) 东财日 K（项目 AkshareQuoteAdapter 使用的 stock_zh_a_hist）
    run_one(
        "stock_zh_a_hist (Eastmoney / 东财)",
        ak.stock_zh_a_hist,
        symbol=symbol_em,
        period="daily",
        start_date=ymd_start,
        end_date=ymd_end,
        adjust="qfq",
        timeout=timeout,
    )

    # 2) 腾讯日 K（AK 封装；与项目直连 Tencent URL 不同，可对比长区间是否可用）
    run_one(
        "stock_zh_a_hist_tx (Tencent via AK / 腾讯-东财封装路径名)",
        ak.stock_zh_a_hist_tx,
        symbol=symbol_tx,
        start_date=ymd_start,
        end_date=ymd_end,
        adjust="qfq",
        timeout=timeout,
    )
    run_one(
        "stock_zh_a_hist_tx (Tencent, dashed dates)",
        ak.stock_zh_a_hist_tx,
        symbol=symbol_tx,
        start_date=dash_start,
        end_date=dash_end,
        adjust="qfq",
        timeout=timeout,
    )

    # 3) 新浪日 K（代码格式 sh600519）
    run_one(
        "stock_zh_a_daily (Sina / 新浪)",
        ak.stock_zh_a_daily,
        symbol=symbol_sina,
        start_date=ymd_start,
        end_date=ymd_end,
        adjust="qfq",
    )

    return results


def main() -> int:
    _ensure_quant_src_on_path()

    parser = argparse.ArgumentParser(description="Probe AKShare A-share daily hist sources.")
    parser.add_argument(
        "--symbol",
        default="600519",
        help="6-digit code for Eastmoney hist (default 600519)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=35,
        help="Natural-day lookback window (default 35)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout seconds (default 30)",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only print dir(ak) candidate names, no network calls",
    )
    args = parser.parse_args()

    symbol_em = (args.symbol or "600519").strip()
    if len(symbol_em) != 6 or not symbol_em.isdigit():
        print("ERROR: --symbol must be a 6-digit A-share code for Eastmoney path.", file=sys.stderr)
        return 2

    prefix = "sh" if symbol_em.startswith(("5", "6", "9")) else "sz"
    symbol_tx = f"{prefix}{symbol_em}"
    symbol_sina = f"{prefix}{symbol_em}"

    import akshare as ak

    ymd_start, ymd_end, dash_start, dash_end = _date_windows(args.days)

    print("=== AKShare 版本 ===")
    print(getattr(ak, "__version__", "unknown"))
    print()
    print("=== 探测窗口 ===")
    print(f"  Eastmoney 日期: {ymd_start} .. {ymd_end}")
    print(f"  备选横杠日期:   {dash_start} .. {dash_end}")
    print(f"  symbol_em={symbol_em}  symbol_tx/sina={symbol_tx}")
    print()

    candidates = _list_akshare_hist_candidates(ak)
    print("=== dir(ak) 中与 A 股 hist/daily 相关的可调用接口（供对照文档）===")
    for n in candidates:
        print(f"  - {n}")
    print()

    if args.list_only:
        return 0

    print("=== 拉取约一个月区间（需外网）===")
    results = run_probes(
        symbol_em=symbol_em,
        symbol_tx=symbol_tx,
        symbol_sina=symbol_sina,
        ymd_start=ymd_start,
        ymd_end=ymd_end,
        dash_start=dash_start,
        dash_end=dash_end,
        timeout=args.timeout,
    )

    for r in results:
        status = "OK" if r.ok else "FAIL"
        print(f"[{status}] {r.name}")
        if r.ok:
            print(f"      rows={r.rows}  columns={list(r.columns)[:12]}{'...' if len(r.columns) > 12 else ''}")
        else:
            print(f"      {r.error}")
        print()

    usable = [r.name for r in results if r.ok]
    print("=== 小结：本窗口内返回非空 DataFrame 的接口 ===")
    if usable:
        for n in usable:
            print(f"  - {n}")
    else:
        print("  (无) — 请检查网络、代理、或调大 --timeout")
    return 0 if usable else 1


if __name__ == "__main__":
    raise SystemExit(main())
