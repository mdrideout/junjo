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
            // Track consecutive pressure checks for duration warning (20 checks = 10 seconds)
            let mut consecutive_pressure_count: u32 = 0;

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

                if is_under_pressure {
                    consecutive_pressure_count += 1;

                    if !was_under_pressure {
                        pressure_flag.store(true, Ordering::Relaxed);
                        warn!(
                            used_mb = used_bytes / 1024 / 1024,
                            max_mb = max_bytes / 1024 / 1024,
                            "Backpressure activated"
                        );
                    }

                    // Warn once after 10 seconds of sustained pressure (20 checks at 500ms)
                    if consecutive_pressure_count == 20 {
                        warn!(
                            used_mb = used_bytes / 1024 / 1024,
                            max_mb = max_bytes / 1024 / 1024,
                            duration_seconds = 10,
                            "Backpressure sustained for 10+ seconds - check if threshold is set too low or investigate other memory issues"
                        );
                    }
                } else {
                    if was_under_pressure {
                        pressure_flag.store(false, Ordering::Relaxed);
                        info!(
                            used_mb = used_bytes / 1024 / 1024,
                            max_mb = max_bytes / 1024 / 1024,
                            "Backpressure released"
                        );
                    }
                    consecutive_pressure_count = 0;
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
