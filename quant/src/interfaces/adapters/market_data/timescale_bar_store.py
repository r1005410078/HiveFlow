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

    def list_sync_runs(
        self,
        days: int,
        timeframe: str | None = None,
        symbols: list[str] | None = None,
        status: str | None = None,
    ) -> list[dict]:
        # MVP: query sync_runs only; symbols filtering is reserved for later join optimization.
        query = """
        select run_id::text as run_id,
               end_date::text as date,
               status,
               timeframe,
               effective_symbols_count as symbols_count
        from sync_runs
        where end_date >= current_date - (%s::int - 1)
        """
        params: list[object] = [days]
        if timeframe:
            query += " and timeframe = %s"
            params.append(timeframe)
        if status:
            query += " and status = %s"
            params.append(status)
        if symbols:
            _ = symbols
        query += " order by end_date desc, started_at desc"

        cur = self._conn.cursor()
        try:
            cur.execute(query, params)
            rows = cur.fetchall()
        finally:
            cur.close()
        return [
            {
                "run_id": row[0],
                "date": row[1],
                "status": row[2],
                "timeframe": row[3],
                "symbols_count": row[4],
                "manifest_id": "",
            }
            for row in rows
        ]

