from __future__ import annotations

import math
import numbers
import re

from interfaces.adapters.market_data.no_http_proxy_env import disabled_http_proxy_env

_INDEX_CODE_MAP = {
    "csi300": "000300",
    "zz500": "000905",
}


class AkshareUniverseAdapter:
    def __init__(self, client=None):
        if client is not None:
            self._ak = client
            return
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("akshare is required for universe sync") from exc
        self._ak = ak

    @staticmethod
    def _normalize_raw_code_cell(code: object) -> str | None:
        """Turn akshare/pandas cell into 6-digit A-share code, or None if unusable.

        EM 行情等接口常见 ``600900.0``（float）、或 ``600900.SH`` 字符串；原逻辑只认 6 位数字，会丢行。
        """
        if code is None:
            return None
        if isinstance(code, bool):
            return None
        if isinstance(code, numbers.Integral):
            n = int(code)
            if n < 0 or n > 999_999:
                return None
            return f"{n:06d}"
        if isinstance(code, float):
            if math.isnan(code) or math.isinf(code):
                return None
            try:
                n = int(round(code))
            except (ValueError, OverflowError):
                return None
            if n < 0 or n > 999_999:
                return None
            return f"{n:06d}"
        text = str(code).strip()
        if not text or text.lower() in ("nan", "none", "nat"):
            return None
        text = re.sub(r"\.(SH|SZ|BJ)$", "", text, flags=re.IGNORECASE)
        if re.fullmatch(r"\d+\.0+", text):
            text = text.split(".", 1)[0]
        if re.fullmatch(r"[0-9]{6}", text):
            return text
        return None

    @staticmethod
    def _to_exchange_symbol(code: str) -> str | None:
        text = str(code).strip()
        if not re.fullmatch(r"[0-9]{6}", text):
            return None
        if text.startswith(("600", "601", "603", "605", "688")):
            return f"{text}.SH"
        if text.startswith(("000", "001", "002", "003", "300", "301")):
            return f"{text}.SZ"
        if text.startswith(("430", "831", "832", "833", "835", "836", "837", "838", "839", "870", "871", "872")):
            return f"{text}.BJ"
        # Fallback: default to SH for unrecognized A-share prefixes.
        return f"{text}.SH"

    @staticmethod
    def _extract_code_column_name(df) -> str | None:
        if df is None or df.empty:
            return None
        for col in ("品种代码", "成分券代码", "代码", "证券代码", "股票代码", "symbol", "code"):
            if col in df.columns:
                return col
        return None

    @staticmethod
    def _extract_name_column_name(df) -> str | None:
        if df is None or df.empty:
            return None
        for col in (
            "品种名称",
            "股票简称",
            "名称",
            "证券简称",
            "股票名称",
            "证券名称",
            "成份股名称",
            "成分股名称",
            "成份券名称",
            "成分券名称",
            "name",
            "Name",
        ):
            if col in df.columns:
                return col
        return None

    @staticmethod
    def _extract_code_column(df):
        col = AkshareUniverseAdapter._extract_code_column_name(df)
        if col is None:
            return []
        return df[col].tolist()

    def _symbol_name_pairs_from_df(self, df) -> list[tuple[str, str]]:
        """Return (exchange_symbol, name_zh) for each row; name may be empty."""
        if df is None or df.empty:
            return []
        code_col = self._extract_code_column_name(df)
        if code_col is None:
            return []
        name_col = self._extract_name_column_name(df)
        codes = df[code_col].tolist()
        names = df[name_col].tolist() if name_col else [""] * len(codes)
        pairs: list[tuple[str, str]] = []
        for code, raw_name in zip(codes, names):
            six = self._normalize_raw_code_cell(code)
            if six is None:
                continue
            sym = self._to_exchange_symbol(six)
            if not sym:
                continue
            name = str(raw_name).strip() if raw_name is not None and str(raw_name).strip() else ""
            pairs.append((sym, name))
        return pairs

    def _fetch_index_constituents_with_names(self, index_code: str) -> list[tuple[str, str]]:
        candidates = (
            ("index_stock_cons", {"symbol": index_code}),
            ("stock_zh_index_cons", {"symbol": index_code}),
            ("index_component_cons", {"symbol": index_code}),
        )
        for method_name, kwargs in candidates:
            fn = getattr(self._ak, method_name, None)
            if fn is None:
                continue
            df = fn(**kwargs)
            pairs = self._symbol_name_pairs_from_df(df)
            if pairs:
                # de-dupe by symbol, keep first name
                seen: dict[str, str] = {}
                for sym, name in pairs:
                    if sym not in seen:
                        seen[sym] = name
                return sorted(seen.items(), key=lambda x: x[0])
        raise RuntimeError(f"akshare cannot fetch constituents for index {index_code}")

    def _fetch_index_constituents(self, index_code: str) -> list[str]:
        return [s for s, _ in self._fetch_index_constituents_with_names(index_code)]

    def _fetch_all_a_with_names(self) -> list[tuple[str, str]]:
        fn = getattr(self._ak, "stock_zh_a_spot_em", None)
        if fn is None:
            raise RuntimeError("akshare method stock_zh_a_spot_em is unavailable")
        df = fn()
        pairs = self._symbol_name_pairs_from_df(df)
        if not pairs:
            raise RuntimeError("akshare returned empty all_a symbols")
        seen: dict[str, str] = {}
        for sym, name in pairs:
            if sym not in seen:
                seen[sym] = name
        return sorted(seen.items(), key=lambda x: x[0])

    @staticmethod
    def _extract_name_from_individual_info_df(df) -> str:
        """Best-effort parse `stock_individual_info_em` DataFrame to a Chinese short name."""
        if df is None or getattr(df, "empty", False):
            return ""
        # Common shape: columns like ["item", "value"] (or Chinese variants)
        cols = [str(c) for c in getattr(df, "columns", [])]
        if len(cols) >= 2:
            key_col = cols[0]
            val_col = cols[1]
            try:
                for _, row in df.iterrows():
                    k = str(row.get(key_col, "")).strip()
                    v = str(row.get(val_col, "")).strip()
                    if not v or v.lower() in ("nan", "none"):
                        continue
                    if any(x in k for x in ("简称", "证券简称", "股票简称", "名称", "证券名称", "股票名称")):
                        return v
            except Exception:
                return ""
        return ""

    def fetch_symbol_name_zh(self, symbol: str) -> str:
        """Fetch a single A-share Chinese short name by 6-digit or exchange symbol.

        This is a fallback for `symbol-names-sync --universe default` to avoid fetching all_a,
        which is large and sometimes disconnected by upstream.
        """
        with disabled_http_proxy_env():
            six = self._normalize_raw_code_cell(symbol)
            if six is None:
                return ""
            fn = getattr(self._ak, "stock_individual_info_em", None)
            if fn is None:
                return ""
            df = fn(symbol=six)
            return self._extract_name_from_individual_info_df(df)

    def _fetch_all_a(self) -> list[str]:
        return [s for s, _ in self._fetch_all_a_with_names()]

    def fetch_universe_symbols_with_names(self, universe: str) -> list[tuple[str, str]]:
        with disabled_http_proxy_env():
            if universe in _INDEX_CODE_MAP:
                return self._fetch_index_constituents_with_names(_INDEX_CODE_MAP[universe])
            if universe == "all_a":
                return self._fetch_all_a_with_names()
            raise ValueError(f"universe {universe} does not support akshare sync")

    def fetch_universe_symbols(self, universe: str) -> list[str]:
        return [s for s, _ in self.fetch_universe_symbols_with_names(universe)]
