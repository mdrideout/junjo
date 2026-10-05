//! Filesystem scan for cold Parquet files.
//!
//! Ingestion writes cold files as
//! `{base}/year=YYYY/month=MM/day=DD/{timestamp}_{suffix}.parquet`, finishing
//! each with an atomic rename from `.parquet.tmp`. Startup reconciliation and
//! the indexer both use this one scan, so they always agree on what counts as
//! an indexable file (ingestion ADR-002).

use std::path::Path;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParquetFile {
    pub path: String,
    pub size_bytes: u64,
}

/// Find every `.parquet` file under `base`, sorted by path. Directories named
/// `tmp` hold ephemeral files and are skipped. A missing base directory is an
/// empty result: ingestion may not have flushed yet.
pub fn scan_parquet_files(base: &Path) -> Vec<ParquetFile> {
    let mut files = Vec::new();
    if !base.exists() {
        tracing::debug!(path = %base.display(), "span storage path does not exist yet");
        return files;
    }
    if !base.is_dir() {
        tracing::warn!(path = %base.display(), "span storage path is not a directory");
        return files;
    }
    scan_directory(base, &mut files);
    files.sort_by(|left, right| left.path.cmp(&right.path));
    files
}

fn scan_directory(directory: &Path, files: &mut Vec<ParquetFile>) {
    let entries = match std::fs::read_dir(directory) {
        Ok(entries) => entries,
        Err(error) => {
            tracing::warn!(path = %directory.display(), %error, "could not read directory");
            return;
        }
    };
    for entry in entries.flatten() {
        let path = entry.path();
        // A file can disappear between listing and inspection.
        let Ok(metadata) = std::fs::metadata(&path) else {
            continue;
        };
        if metadata.is_dir() {
            if entry.file_name() != "tmp" {
                scan_directory(&path, files);
            }
            continue;
        }
        if path.extension().and_then(|extension| extension.to_str()) != Some("parquet") {
            continue;
        }
        match path.to_str() {
            Some(path) => files.push(ParquetFile {
                path: path.to_string(),
                size_bytes: metadata.len(),
            }),
            None => {
                tracing::warn!(path = %path.display(), "skipping Parquet file with a non-UTF-8 path");
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn partitioned_files_are_found_and_temporary_files_are_skipped() {
        let directory = tempfile::tempdir().unwrap();
        let base = directory.path();
        let day = base.join("year=2026/month=10/day=03");
        std::fs::create_dir_all(&day).unwrap();
        std::fs::create_dir_all(base.join("tmp")).unwrap();
        std::fs::write(day.join("b.parquet"), b"12").unwrap();
        std::fs::write(day.join("a.parquet"), b"1234").unwrap();
        std::fs::write(day.join("in-progress.parquet.tmp"), b"1").unwrap();
        std::fs::write(day.join("notes.txt"), b"1").unwrap();
        std::fs::write(base.join("tmp/warm.parquet"), b"1").unwrap();

        let files = scan_parquet_files(base);

        let names: Vec<&str> = files
            .iter()
            .map(|file| file.path.rsplit('/').next().unwrap())
            .collect();
        assert_eq!(names, ["a.parquet", "b.parquet"]);
        assert_eq!(files[0].size_bytes, 4);
    }

    #[test]
    fn a_missing_or_non_directory_base_is_an_empty_result() {
        let directory = tempfile::tempdir().unwrap();
        assert!(scan_parquet_files(&directory.path().join("missing")).is_empty());
        let file = directory.path().join("file");
        std::fs::write(&file, b"1").unwrap();
        assert!(scan_parquet_files(&file).is_empty());
    }
}
