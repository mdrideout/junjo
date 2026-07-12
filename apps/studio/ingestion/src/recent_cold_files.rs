use std::collections::VecDeque;
use std::time::{Duration, Instant};

/// In-memory tracker for recently flushed cold Parquet files.
///
/// This exists to close the visibility gap where:
/// 1) WAL data is flushed to a new cold Parquet file
/// 2) The backend has not yet indexed the file into SQLite metadata
/// 3) The WAL is now empty (so the HOT snapshot may be empty)
///
/// The ingestion service is the source of truth for this "recent cold" bridge
/// by returning these paths from PrepareHotSnapshot.
pub struct RecentColdFiles {
    max_files: usize,
    max_age: Duration,
    entries: VecDeque<_Entry>,
}

struct _Entry {
    path: String,
    recorded_at: Instant,
}

impl RecentColdFiles {
    pub fn new(max_files: usize, max_age: Duration) -> Self {
        Self {
            max_files,
            max_age,
            entries: VecDeque::with_capacity(max_files.min(1024)),
        }
    }

    pub fn record(&mut self, path: String) {
        if self.max_files == 0 {
            return;
        }

        self.prune_expired();

        // Deduplicate to keep most recent at the front.
        self.entries.retain(|e| e.path != path);

        self.entries.push_front(_Entry {
            path,
            recorded_at: Instant::now(),
        });

        self.prune_to_limit();
    }

    pub fn list(&mut self) -> Vec<String> {
        self.prune_expired();
        self.entries.iter().map(|e| e.path.clone()).collect()
    }

    fn prune_to_limit(&mut self) {
        while self.entries.len() > self.max_files {
            self.entries.pop_back();
        }
    }

    fn prune_expired(&mut self) {
        if self.max_age.is_zero() {
            return;
        }

        let now = Instant::now();
        self.entries
            .retain(|e| now.duration_since(e.recorded_at) <= self.max_age);
    }
}
