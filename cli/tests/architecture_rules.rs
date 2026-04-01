use std::fs;
use std::path::{Path, PathBuf};

fn read(path: &Path) -> String {
    fs::read_to_string(path).expect("read source file")
}

fn src_path(rel: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src").join(rel)
}

#[test]
fn cmd_layer_must_not_import_infrastructure() {
    let cmd_files = ["cmd/data.rs", "cmd/pipeline.rs"];
    for file in cmd_files {
        let content = read(&src_path(file));
        assert!(
            !content.contains("crate::infrastructure"),
            "cmd layer must not import infrastructure directly: {file}"
        );
    }
}

#[test]
fn domain_layer_must_not_depend_on_io_or_frameworks() {
    let domain_files = ["domain/command.rs", "domain/result.rs", "domain/mod.rs"];
    for file in domain_files {
        let content = read(&src_path(file));
        let forbidden = [
            "crate::infrastructure",
            "crate::cmd",
            "crate::application",
            "reqwest::",
            "clap::",
            "std::process::Command",
        ];
        for pat in forbidden {
            assert!(
                !content.contains(pat),
                "domain layer contains forbidden dependency '{pat}': {file}"
            );
        }
    }
}

