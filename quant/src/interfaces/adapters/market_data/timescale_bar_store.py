from __future__ import annotations

import hashlib
import json


_SYNC_RUN_COLUMNS = (
    "run_id::text, request_id, status, days, end_date::text, timeframe,"
    " selection_mode, symbols_hash, effective_symbols_count, written_rows,"
    " manifest_ids, started_at::text, finished_at::text, error_code, error_message,"
    " phase, progress, cancel_requested_at::text"
)

_SYNC_RUN_KEYS = (
    "run_id", "request_id", "status", "days", "end_date", "timeframe",
    "selection_mode", "symbols_hash", "effective_symbols_count", "written_rows",
    "manifest_ids", "started_at", "finished_at", "error_code", "error_message",
    "phase", "progress", "cancel_requested_at",
)


def _row_to_run_dict(row: tuple) -> dict:
    d = dict(zip(_SYNC_RUN_KEYS, row))
    d["manifest_ids"] = d.get("manifest_ids") or []
    if isinstance(d.get("progress"), str):
        try:
            d["progress"] = json.loads(d["progress"])
        except (json.JSONDecodeError, TypeError):
            d["progress"] = {}
    d.setdefault("progress", {})
    return d


def enrich_sync_run_dict(d: dict) -> dict:
    """When async insert used placeholders (universe/default), DB may still show
    effective_symbols_count=0 and empty symbols_hash until finalize runs; also helps
    older rows. Derive from progress JSON for API/CLI consistency."""
    out = dict(d)
    prog = out.get("progress")
    if not isinstance(prog, dict):
        return out
    mode = out.get("selection_mode")
    if mode not in ("universe", "default"):
        return out
    if out.get("effective_symbols_count", 0) == 0:
        ts = prog.get("total_symbols")
        if isinstance(ts, int) and ts > 0:
            out["effective_symbols_count"] = ts
    if not out.get("symbols_hash"):
        done = prog.get("symbols_done_for_run") or []
        pend = prog.get("symbols_pending_for_run") or []
        if isinstance(done, list) and isinstance(pend, list):
            syms = sorted(
                {str(s) for s in done if s} | {str(s) for s in pend if s}
            )
            if syms:
                out["symbols_hash"] = hashlib.sha256(",".join(syms).encode()).hexdigest()
    return out


class TimescaleBarStore:
    """Timescale 存储适配器（MVP：通过 DB-API 连接对象执行 SQL）。"""

    def __init__(self, conn):
        self._conn = conn

    def upsert_bars(self, rows: list[dict]) -> int:
        if not rows:
            return 0

        sql = """
        insert into bars (
          symbol, timeframe, bar_time, open, high, low, close,
          volume, amount, adj_factor, data_source
        ) values (
          %(symbol)s, %(timeframe)s, %(bar_time)s, %(open)s, %(high)s, %(low)s, %(close)s,
          %(volume)s, %(amount)s, %(adj_factor)s, %(data_source)s
        )
        on conflict (symbol, timeframe, bar_time)
        do update set
          open = excluded.open,
          high = excluded.high,
          low = excluded.low,
          close = excluded.close,
          volume = excluded.volume,
          amount = excluded.amount,
          adj_factor = excluded.adj_factor,
          data_source = excluded.data_source,
          ingested_at = now()
        """

        cur = self._conn.cursor()
        try:
            for row in rows:
                cur.execute(sql, row)
            self._conn.commit()
        finally:
            cur.close()
        return len(rows)

    def get_sync_run_by_request_id(self, request_id: str) -> dict | None:
        sql = f"select {_SYNC_RUN_COLUMNS} from sync_runs where request_id = %s limit 1"
        cur = self._conn.cursor()
        try:
            cur.execute(sql, [request_id])
            row = cur.fetchone()
        finally:
            cur.close()
        return enrich_sync_run_dict(_row_to_run_dict(row)) if row else None

    def get_checkpoints(self, symbols: list[str], timeframe: str) -> dict[str, str]:
        if not symbols:
            return {}
        sql = """
        select symbol, last_bar_time::text
        from sync_checkpoints
        where timeframe = %s and symbol = any(%s)
        """
        cur = self._conn.cursor()
        try:
            cur.execute(sql, [timeframe, symbols])
            rows = cur.fetchall()
        finally:
            cur.close()
        return {row[0]: row[1] for row in rows}

    def upsert_checkpoints(self, checkpoints: list[dict]) -> None:
        if not checkpoints:
            return
        sql = """
        insert into sync_checkpoints (symbol, timeframe, last_bar_time, last_run_id)
        values (%(symbol)s, %(timeframe)s, %(last_bar_time)s, %(last_run_id)s)
        on conflict (symbol, timeframe)
        do update set
          last_bar_time = excluded.last_bar_time,
          last_run_id = excluded.last_run_id,
          updated_at = now()
        """
        cur = self._conn.cursor()
        try:
            for item in checkpoints:
                cur.execute(sql, item)
            self._conn.commit()
        finally:
            cur.close()

    def insert_sync_run(self, payload: dict) -> None:
        sql = """
        insert into sync_runs (
          run_id, request_id, status, days, end_date, timeframe,
          selection_mode, symbols_hash, effective_symbols_count, written_rows,
          manifest_ids, error_code, error_message, finished_at
        ) values (
          %(run_id)s, %(request_id)s, %(status)s, %(days)s, %(end_date)s, %(timeframe)s,
          %(selection_mode)s, %(symbols_hash)s, %(effective_symbols_count)s, %(written_rows)s,
          %(manifest_ids)s, %(error_code)s, %(error_message)s, now()
        )
        on conflict (run_id)
        do update set
          status = excluded.status,
          selection_mode = excluded.selection_mode,
          written_rows = excluded.written_rows,
          manifest_ids = excluded.manifest_ids,
          error_code = excluded.error_code,
          error_message = excluded.error_message,
          finished_at = now()
        """
        cur = self._conn.cursor()
        try:
            cur.execute(sql, payload)
            self._conn.commit()
        finally:
            cur.close()

    def list_sync_runs(
        self,
        days: int,
        timeframe: str | None = None,
        status: str | None = None,
        request_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        query = f"""
        select {_SYNC_RUN_COLUMNS}
        from sync_runs
        where started_at >= (current_date - (%s::int - 1))::timestamptz
        """
        params: list[object] = [days]
        if timeframe:
            query += " and timeframe = %s"
            params.append(timeframe)
        if status:
            query += " and status = %s"
            params.append(status)
        if request_id:
            query += " and request_id = %s"
            params.append(request_id)
        query += " order by started_at desc limit %s"
        params.append(limit or 100)

        cur = self._conn.cursor()
        try:
            cur.execute(query, params)
            rows = cur.fetchall()
        finally:
            cur.close()
        return [enrich_sync_run_dict(_row_to_run_dict(row)) for row in rows]

    # ── async sync 专用方法 ──────────────────────────────────────

    def insert_sync_run_running(self, payload: dict) -> None:
        """创建 status=running 的 sync_run（用于异步提交）。"""
        sql = """
        insert into sync_runs (
          run_id, request_id, status, phase, days, end_date, timeframe,
          selection_mode, symbols_hash, effective_symbols_count, written_rows,
          manifest_ids, error_code, error_message, progress
        ) values (
          %(run_id)s, %(request_id)s, 'running', %(phase)s,
          %(days)s, %(end_date)s, %(timeframe)s,
          %(selection_mode)s, %(symbols_hash)s, %(effective_symbols_count)s, 0,
          %(manifest_ids)s, null, null, %(progress)s::jsonb
        )
        """
        cur = self._conn.cursor()
        try:
            params = dict(payload)
            params.setdefault("phase", "pending")
            params.setdefault("progress", "{}")
            if isinstance(params["progress"], dict):
                params["progress"] = json.dumps(params["progress"])
            cur.execute(sql, params)
            self._conn.commit()
        finally:
            cur.close()

    def get_sync_run_by_id(self, run_id: str) -> dict | None:
        sql = f"select {_SYNC_RUN_COLUMNS} from sync_runs where run_id = %s::uuid"
        cur = self._conn.cursor()
        try:
            cur.execute(sql, [run_id])
            row = cur.fetchone()
        finally:
            cur.close()
        return enrich_sync_run_dict(_row_to_run_dict(row)) if row else None

    def get_running_sync_run(self) -> dict | None:
        sql = f"select {_SYNC_RUN_COLUMNS} from sync_runs where status = 'running' order by started_at desc limit 1"
        cur = self._conn.cursor()
        try:
            cur.execute(sql)
            row = cur.fetchone()
        finally:
            cur.close()
        return enrich_sync_run_dict(_row_to_run_dict(row)) if row else None

    def update_sync_progress(self, run_id: str, phase: str, progress: dict) -> None:
        sql = """
        update sync_runs
        set phase = %s, progress = %s::jsonb
        where run_id = %s::uuid
        """
        cur = self._conn.cursor()
        try:
            cur.execute(sql, [phase, json.dumps(progress), run_id])
            self._conn.commit()
        finally:
            cur.close()

    def finalize_sync_run(
        self,
        run_id: str,
        status: str,
        *,
        written_rows: int = 0,
        manifest_ids: list[str] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        phase: str | None = None,
        progress: dict | None = None,
        effective_symbols_count: int | None = None,
        symbols_hash: str | None = None,
    ) -> None:
        """Persist terminal state. Optionally refresh symbol stats resolved at runtime (universe/default)."""
        final_phase = phase or status
        set_parts = [
            "status = %s",
            "phase = %s",
            "written_rows = %s",
            "manifest_ids = %s",
            "error_code = %s",
            "error_message = %s",
            "progress = %s::jsonb",
            "finished_at = now()",
        ]
        params: list[object] = [
            status,
            final_phase,
            written_rows,
            manifest_ids or [],
            error_code,
            error_message,
            json.dumps(progress or {}),
        ]
        if effective_symbols_count is not None:
            set_parts.append("effective_symbols_count = %s")
            params.append(effective_symbols_count)
        if symbols_hash is not None:
            set_parts.append("symbols_hash = %s")
            params.append(symbols_hash)
        params.append(run_id)
        sql = f"""
        update sync_runs
        set {", ".join(set_parts)}
        where run_id = %s::uuid
        """
        cur = self._conn.cursor()
        try:
            cur.execute(sql, params)
            self._conn.commit()
        finally:
            cur.close()

    def request_sync_cancel(self, run_id: str) -> bool:
        """Set cancel_requested_at if still running. Returns True if accepted."""
        sql = """
        update sync_runs
        set cancel_requested_at = now()
        where run_id = %s::uuid and status = 'running' and cancel_requested_at is null
        """
        cur = self._conn.cursor()
        try:
            cur.execute(sql, [run_id])
            affected = cur.rowcount
            self._conn.commit()
        finally:
            cur.close()
        return affected > 0

    def mark_orphan_runs_interrupted(self) -> int:
        """Startup 收口：将所有 status=running 的行标记为 interrupted。"""
        sql = """
        update sync_runs
        set status = 'interrupted',
            phase = 'interrupted',
            error_code = 'SYNC_ORPHAN_RUN',
            error_message = 'process restarted while sync was running',
            finished_at = now()
        where status = 'running'
        """
        cur = self._conn.cursor()
        try:
            cur.execute(sql)
            affected = cur.rowcount
            self._conn.commit()
        finally:
            cur.close()
        return affected

    # ── symbol failure audit ──────────────────────────────────

    def upsert_symbol_failure(
        self,
        run_id: str,
        symbol: str,
        error_code: str,
        error_message: str,
        failed_day: str,
    ) -> None:
        sql = """
        insert into sync_run_symbol_failures
          (run_id, symbol, attempt_count, last_error_code, last_error_message, last_failed_day)
        values (%s::uuid, %s, 1, %s, %s, %s::date)
        on conflict (run_id, symbol) do update set
          attempt_count = sync_run_symbol_failures.attempt_count + 1,
          last_error_code = excluded.last_error_code,
          last_error_message = excluded.last_error_message,
          last_failed_day = excluded.last_failed_day,
          last_failed_at = now()
        """
        cur = self._conn.cursor()
        try:
            cur.execute(sql, [run_id, symbol, error_code, error_message, failed_day])
            self._conn.commit()
        finally:
            cur.close()

    def list_failed_symbols_for_retry(self, run_id: str, min_attempts: int = 3) -> list[dict]:
        """返回超过重试阈值的 terminal 失败标的。"""
        sql = """
        select symbol, attempt_count, last_error_code, last_error_message,
               last_failed_day::text, first_failed_at::text, last_failed_at::text
        from sync_run_symbol_failures
        where run_id = %s::uuid and attempt_count >= %s
        order by symbol
        """
        cur = self._conn.cursor()
        try:
            cur.execute(sql, [run_id, min_attempts])
            rows = cur.fetchall()
        finally:
            cur.close()
        return [
            {
                "symbol": r[0],
                "attempt_count": r[1],
                "last_error_code": r[2],
                "last_error_message": r[3],
                "last_failed_day": r[4],
                "first_failed_at": r[5],
                "last_failed_at": r[6],
            }
            for r in rows
        ]

    def clear_symbol_failure(self, run_id: str, symbol: str) -> None:
        sql = "delete from sync_run_symbol_failures where run_id = %s::uuid and symbol = %s"
        cur = self._conn.cursor()
        try:
            cur.execute(sql, [run_id, symbol])
            self._conn.commit()
        finally:
            cur.close()

    # ── 原有读方法 ────────────────────────────────────────────

    def list_bars(
        self,
        symbols: list[str] | None = None,
        timeframe: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        query = """
        select symbol, timeframe, bar_time::text, open, high, low, close,
               volume, amount, adj_factor, data_source
        from bars
        where 1=1
        """
        params: list[object] = []
        if timeframe:
            query += " and timeframe = %s"
            params.append(timeframe)
        if symbols:
            query += " and symbol = any(%s)"
            params.append(symbols)
        if start_date:
            query += " and bar_time >= %s::timestamptz"
            params.append(f"{start_date}T00:00:00+08:00")
        if end_date:
            query += " and bar_time <= %s::timestamptz"
            params.append(f"{end_date}T23:59:59+08:00")
        query += " order by bar_time desc, symbol asc limit %s"
        params.append(limit or 5000)

        cur = self._conn.cursor()
        try:
            cur.execute(query, params)
            rows = cur.fetchall()
        finally:
            cur.close()
        return [
            {
                "symbol": row[0],
                "timeframe": row[1],
                "bar_time": row[2],
                "open": row[3],
                "high": row[4],
                "low": row[5],
                "close": row[6],
                "volume": row[7],
                "amount": row[8],
                "adj_factor": row[9],
                "data_source": row[10],
            }
            for row in rows
        ]
