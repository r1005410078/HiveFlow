from __future__ import annotations

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
            sym = self._to_exchange_symbol(code)
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
