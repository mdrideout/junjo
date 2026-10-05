//! Shared access to the telemetry contract fixtures.
#![allow(dead_code)]

use std::path::{Path, PathBuf};

use junjo_evidence::json::{Json, JsonObject};

/// The monorepo root. The workspace sits four directories below it.
pub fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../..")
        .canonicalize()
        .expect("the repository root exists")
}

pub fn fixture_root() -> PathBuf {
    repository_root().join("contracts/telemetry/fixtures")
}

pub fn read_json(path: &Path) -> Json {
    let text = std::fs::read_to_string(path)
        .unwrap_or_else(|error| panic!("cannot read {}: {error}", path.display()));
    serde_json::from_str(&text)
        .unwrap_or_else(|error| panic!("cannot parse {}: {error}", path.display()))
}

/// Every `*.json` file directly inside `directory`, in name order.
pub fn json_files(directory: &Path) -> Vec<PathBuf> {
    let mut paths: Vec<PathBuf> = std::fs::read_dir(directory)
        .unwrap_or_else(|error| panic!("cannot list {}: {error}", directory.display()))
        .map(|entry| entry.expect("a directory entry").path())
        .filter(|path| {
            path.extension()
                .is_some_and(|extension| extension == "json")
        })
        .collect();
    paths.sort();
    paths
}

pub fn file_stem(path: &Path) -> String {
    path.file_stem()
        .expect("a file name")
        .to_string_lossy()
        .into_owned()
}

/// The spans of one fixture envelope.
pub fn spans(fixture: &Json) -> Vec<&JsonObject> {
    fixture["spans"]
        .as_array()
        .expect("fixture spans")
        .iter()
        .map(|span| span.as_object().expect("a span object"))
        .collect()
}

pub fn span_type(span: &JsonObject) -> Option<&str> {
    span.get("attributes_json")?
        .get("junjo.span_type")?
        .as_str()
}
