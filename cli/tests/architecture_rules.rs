use std::fs;
use std::path::{Path, PathBuf};

fn read(path: &Path) -> String {
    fs::read_to_string(path).expect("read source file")
}

fn src_path(rel: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src").join(rel)
}

fn visit_rs_files(dir: &Path, files: &mut Vec<PathBuf>) {
    for entry in fs::read_dir(dir).expect("read dir") {
        let entry = entry.expect("dir entry");
        let path = entry.path();
        if path.is_dir() {
            visit_rs_files(&path, files);
        } else if path.extension().and_then(|ext| ext.to_str()) == Some("rs") {
            files.push(path);
        }
    }
}

#[test]
fn cmd_layer_must_not_import_infrastructure() {
    let cmd_files = [
        "cmd/config.rs",
        "cmd/data.rs",
        "cmd/execution.rs",
        "cmd/pipeline.rs",
        "cmd/factor.rs",
        "cmd/monitor.rs",
        "cmd/portfolio.rs",
        "cmd/signal.rs",
        "cmd/task.rs",
        "cmd/tui.rs",
    ];
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
    let domain_files = [
        "domain/bars_aggregate.rs",
        "domain/command.rs",
        "domain/result.rs",
        "domain/mod.rs",
    ];
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

#[test]
fn application_layer_must_not_import_cmd_types() {
    let mut files = Vec::new();
    visit_rs_files(&src_path("application"), &mut files);
    for file in files {
        let content = read(&file);
        assert!(
            !content.contains("crate::cmd"),
            "application layer must not import cmd types directly: {}",
            file.display()
        );
    }
}
