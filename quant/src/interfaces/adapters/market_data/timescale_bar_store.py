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
        symbols: list[str] | None = None,
        status: str | None = None,
    ) -> list[dict]:
        # Data-query returns market bars for recent window (time + price first).
        if status and status != "success":
            return []
        query = """
        select bar_time::text as bar_time,
               symbol,
               timeframe,
               open,
               high,
               low,
               close,
               volume,
               amount,
               data_source
        from bars
        where bar_time >= (current_date - (%s::int - 1))::timestamptz
        """
        params: list[object] = [days]
        if timeframe:
            query += " and timeframe = %s"
            params.append(timeframe)
        if symbols:
            query += " and symbol = any(%s)"
            params.append(symbols)
        query += """
        order by bar_time desc, symbol asc
        limit 5000
        """

        cur = self._conn.cursor()
        try:
            cur.execute(query, params)
            rows = cur.fetchall()
        finally:
            cur.close()
        return [
            {
                "run_id": f"bar_{row[1]}_{row[0]}",
                "bar_time": row[0],
                "symbol": row[1],
                "status": "success",
                "timeframe": row[2],
                "open": row[3],
                "high": row[4],
                "low": row[5],
                "close": row[6],
                "volume": row[7],
                "amount": row[8],
                "data_source": row[9],
                "manifest_id": "",
            }
            for row in rows
        ]
