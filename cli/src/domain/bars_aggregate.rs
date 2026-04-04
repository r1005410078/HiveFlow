//! OHLC 按时间顺序连续分桶聚合（用于 TUI 大图点数上限）。无 IO。

#[derive(Debug, Clone, PartialEq)]
pub struct OhlcPoint {
    pub bar_time: String,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
}

/// `max_points == 0`：调用方应视为「不聚合」并直接使用原序列。
/// `len <= max_points`：返回原序列拷贝。
/// 否则：`chunk = ceil(n / max_points)`，连续 `chunk` 根合并为一根（open 首、high max、low min、close 末、时间末）。
pub fn aggregate_ohlc_time_order(points: &[OhlcPoint], max_points: usize) -> Vec<OhlcPoint> {
    if max_points == 0 || points.len() <= max_points {
        return points.to_vec();
    }
    let n = points.len();
    let m = max_points;
    let chunk = (n + m - 1) / m;
    let mut out = Vec::with_capacity(m.min(n));
    let mut start = 0usize;
    while start < n {
        let end = (start + chunk).min(n);
        let slice = &points[start..end];
        let first = &slice[0];
        let last = slice.last().expect("non-empty slice");
        let high = slice
            .iter()
            .map(|p| p.high)
            .fold(f64::NEG_INFINITY, f64::max);
        let low = slice
            .iter()
            .map(|p| p.low)
            .fold(f64::INFINITY, f64::min);
        out.push(OhlcPoint {
            bar_time: last.bar_time.clone(),
            open: first.open,
            high,
            low,
            close: last.close,
        });
        start = end;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pt(t: &str, o: f64, h: f64, l: f64, c: f64) -> OhlcPoint {
        OhlcPoint {
            bar_time: t.to_string(),
            open: o,
            high: h,
            low: l,
            close: c,
        }
    }

    #[test]
    fn no_op_when_under_cap() {
        let v = vec![pt("a", 1.0, 2.0, 0.5, 1.5), pt("b", 1.5, 2.5, 1.0, 2.0)];
        let out = aggregate_ohlc_time_order(&v, 10);
        assert_eq!(out, v);
    }

    #[test]
    fn zero_max_means_caller_skip() {
        let v = vec![pt("a", 1.0, 1.0, 1.0, 1.0), pt("b", 2.0, 2.0, 2.0, 2.0)];
        let out = aggregate_ohlc_time_order(&v, 0);
        assert_eq!(out.len(), 2);
    }

    #[test]
    fn ten_buckets_from_thousand() {
        let pts: Vec<OhlcPoint> = (0..1000)
            .map(|i| {
                let x = i as f64;
                pt(
                    &format!("t{i}"),
                    x,
                    x + 1.0,
                    x - 1.0,
                    x + 0.5,
                )
            })
            .collect();
        let out = aggregate_ohlc_time_order(&pts, 10);
        assert_eq!(out.len(), 10);
        assert_eq!(out[0].open, 0.0);
        assert_eq!(out[9].close, pts[999].close);
        let chunk = 100;
        for b in 0..10 {
            let start = b * chunk;
            let end = ((b + 1) * chunk).min(1000);
            let slice = &pts[start..end];
            let expect_high = slice.iter().map(|p| p.high).fold(f64::NEG_INFINITY, f64::max);
            assert!((out[b].high - expect_high).abs() < 1e-9);
        }
    }

    #[test]
    fn two_point_bucket_ohlc() {
        let v = vec![
            pt("t0", 10.0, 11.0, 9.0, 10.5),
            pt("t1", 10.5, 12.0, 10.0, 11.5),
        ];
        let out = aggregate_ohlc_time_order(&v, 1);
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].open, 10.0);
        assert_eq!(out[0].high, 12.0);
        assert_eq!(out[0].low, 9.0);
        assert_eq!(out[0].close, 11.5);
        assert_eq!(out[0].bar_time, "t1");
    }
}
