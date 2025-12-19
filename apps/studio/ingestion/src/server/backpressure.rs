use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use sysinfo::{ProcessesToUpdate, System};
use tracing::{info, warn};

/// Monitors memory usage and applies backpressure when threshold exceeded.
/// Uses a background task to avoid blocking the hot path.
pub struct BackpressureMonitor {
    /// Current backpressure state (updated by background task)
    under_pressure: Arc<AtomicBool>,
}

impl BackpressureMonitor {
    pub fn new(max_bytes: u64) -> Self {
        let under_pressure = Arc::new(AtomicBool::new(false));

        // Spawn background task to periodically check memory
        let pressure_flag = Arc::clone(&under_pressure);
        tokio::spawn(async move {
            let mut sys = System::new();
            let pid = sysinfo::get_current_pid().ok();

            loop {
                sys.refresh_memory();

                // Get process memory usage
                let used_bytes = pid
                    .and_then(|p| {
                        sys.refresh_processes(ProcessesToUpdate::Some(&[p]), false);
                        sys.process(p).map(|proc| proc.memory())
                    })
                    .unwrap_or(0);

                let was_under_pressure = pressure_flag.load(Ordering::Relaxed);
                let is_under_pressure = used_bytes > max_bytes;

                if is_under_pressure != was_under_pressure {
                    pressure_flag.store(is_under_pressure, Ordering::Relaxed);
                    if is_under_pressure {
                        warn!(
                            used_mb = used_bytes / 1024 / 1024,
                            max_mb = max_bytes / 1024 / 1024,
                            "Backpressure activated"
                        );
                    } else {
                        info!(
                            used_mb = used_bytes / 1024 / 1024,
                            max_mb = max_bytes / 1024 / 1024,
                            "Backpressure released"
                        );
                    }
                }

                tokio::time::sleep(Duration::from_millis(500)).await;
            }
        });

        Self { under_pressure }
    }

    /// Fast check - just reads AtomicBool, no syscalls.
    pub fn is_under_pressure(&self) -> bool {
        self.under_pressure.load(Ordering::Relaxed)
    }
}
