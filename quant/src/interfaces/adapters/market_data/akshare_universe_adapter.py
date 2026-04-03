from __future__ import annotations

import re


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
    def _extract_code_column(df):
        if df is None or df.empty:
            return []
        for col in ("品种代码", "成分券代码", "代码", "证券代码", "股票代码", "symbol", "code"):
            if col in df.columns:
                return df[col].tolist()
        return []

    def _fetch_index_constituents(self, index_code: str) -> list[str]:
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
            codes = self._extract_code_column(df)
            symbols = [s for s in (self._to_exchange_symbol(x) for x in codes) if s]
            if symbols:
                return sorted(set(symbols))
        raise RuntimeError(f"akshare cannot fetch constituents for index {index_code}")

    def _fetch_all_a(self) -> list[str]:
        fn = getattr(self._ak, "stock_zh_a_spot_em", None)
        if fn is None:
            raise RuntimeError("akshare method stock_zh_a_spot_em is unavailable")
        df = fn()
        codes = self._extract_code_column(df)
        symbols = [s for s in (self._to_exchange_symbol(x) for x in codes) if s]
        if not symbols:
            raise RuntimeError("akshare returned empty all_a symbols")
        return sorted(set(symbols))

    def fetch_universe_symbols(self, universe: str) -> list[str]:
        if universe in _INDEX_CODE_MAP:
            return self._fetch_index_constituents(_INDEX_CODE_MAP[universe])
        if universe == "all_a":
            return self._fetch_all_a()
        raise ValueError(f"universe {universe} does not support akshare sync")
