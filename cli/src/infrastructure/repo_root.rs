use std::env;
use std::path::{Path, PathBuf};

/// Resolve HiveFlow repository root (directory containing `quant/config/universes`).
pub fn hiveflow_repo_root() -> Option<PathBuf> {
    for key in ["HIVEFLOW_ROOT", "HIVEFLOW_REPO_ROOT"] {
        if let Ok(p) = env::var(key) {
            let pb = PathBuf::from(p.trim());
            if universes_dir(&pb).is_dir() {
                return Some(pb);
            }
        }
    }

    if let Ok(cwd) = env::current_dir() {
        if let Some(root) = walk_up_find_universes(&cwd) {
            return Some(root);
        }
    }

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    if let Some(root) = walk_up_find_universes(&manifest_dir) {
        return Some(root);
    }

    None
}

fn universes_dir(root: &Path) -> PathBuf {
    root.join("quant").join("config").join("universes")
}

fn walk_up_find_universes(start: &Path) -> Option<PathBuf> {
    let mut cur = start.to_path_buf();
    loop {
        if universes_dir(&cur).is_dir() {
            return Some(cur);
        }
        if !cur.pop() {
            break;
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn hiveflow_repo_root_finds_universes_from_manifest_walk_up() {
        let root = hiveflow_repo_root().expect("repo root from CARGO_MANIFEST_DIR / cwd walk-up");
        assert!(
            universes_dir(&root).is_dir(),
            "expected {} to exist",
            universes_dir(&root).display()
        );
    }

    #[test]
    fn walk_up_finds_root_from_nested_path() {
        let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let nested = manifest.join("src").join("infrastructure");
        let root = walk_up_find_universes(&nested).expect("walk-up from cli/src/infrastructure");
        assert!(universes_dir(&root).is_dir());
    }
}
