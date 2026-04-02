from __future__ import annotations


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
        sql = """
        select run_id::text, request_id, status, days, end_date::text, timeframe,
               effective_symbols_count, started_at::text, finished_at::text,
               error_code, error_message
        from sync_runs
        where request_id = %s
        limit 1
        """
        cur = self._conn.cursor()
        try:
            cur.execute(sql, [request_id])
            row = cur.fetchone()
        finally:
            cur.close()
        if row is None:
            return None
        return {
            "run_id": row[0],
            "request_id": row[1],
            "status": row[2],
            "days": row[3],
            "end_date": row[4],
            "timeframe": row[5],
            "effective_symbols_count": row[6],
            "started_at": row[7],
            "finished_at": row[8],
            "error_code": row[9],
            "error_message": row[10],
        }

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
          symbols_hash, effective_symbols_count, error_code, error_message, finished_at
        ) values (
          %(run_id)s, %(request_id)s, %(status)s, %(days)s, %(end_date)s, %(timeframe)s,
          %(symbols_hash)s, %(effective_symbols_count)s, %(error_code)s, %(error_message)s, now()
        )
        on conflict (run_id)
        do update set
          status = excluded.status,
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
        query = """
        select run_id::text, request_id, status, days, end_date::text, timeframe,
               effective_symbols_count, started_at::text, finished_at::text,
               error_code, error_message
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
        query += """
        order by started_at desc
        """
        query += " limit %s"
        params.append(limit or 100)

        cur = self._conn.cursor()
        try:
            cur.execute(query, params)
            rows = cur.fetchall()
        finally:
            cur.close()
        return [
            {
                "run_id": row[0],
                "request_id": row[1],
                "status": row[2],
                "days": row[3],
                "end_date": row[4],
                "timeframe": row[5],
                "effective_symbols_count": row[6],
                "started_at": row[7],
                "finished_at": row[8],
                "error_code": row[9],
                "error_message": row[10],
            }
            for row in rows
        ]

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
