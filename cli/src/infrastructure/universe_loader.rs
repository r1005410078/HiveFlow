use std::collections::BTreeSet;
use std::fs;
use std::path::Path;

use crate::error::AppError;

/// Load symbol list from `quant/config/universes/{name}.txt` under `repo_root`.
pub fn load_universe_symbols(repo_root: &Path, name: &str) -> Result<Vec<String>, AppError> {
    let path = repo_root
        .join("quant")
        .join("config")
        .join("universes")
        .join(format!("{name}.txt"));
    if !path.is_file() {
        return Err(AppError::InvalidArgs(format!(
            "universe file not found: {} (set HIVEFLOW_ROOT or run from repo root)",
            path.display()
        )));
    }
    let raw = fs::read_to_string(&path).map_err(|e| {
        AppError::InvalidArgs(format!("read universe {}: {e}", path.display()))
    })?;
    let mut out = BTreeSet::new();
    for line in raw.lines() {
        let s = line.trim();
        if s.is_empty() || s.starts_with('#') {
            continue;
        }
        out.insert(s.to_string());
    }
    if out.is_empty() {
        return Err(AppError::InvalidArgs(format!(
            "universe {name} has no symbols in {}",
            path.display()
        )));
    }
    Ok(out.into_iter().collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn load_universe_skips_comments_and_empty() {
        let n = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("hf_u_{n}"));
        fs::create_dir_all(root.join("quant/config/universes")).unwrap();
        fs::write(
            root.join("quant/config/universes/test_u.txt"),
            "# c\n600519.SH\n\n000001.SZ\n",
        )
        .unwrap();
        let syms = load_universe_symbols(&root, "test_u").unwrap();
        let _ = fs::remove_dir_all(&root);
        assert_eq!(syms, vec!["000001.SZ".to_string(), "600519.SH".to_string()]);
    }
}
