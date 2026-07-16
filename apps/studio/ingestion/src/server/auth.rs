use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Weak};
use std::time::Duration;

use tokio::sync::{watch, Mutex, Semaphore};
use tokio::time::{timeout, Instant};
use tonic::{Request, Status};
use tracing::{debug, info, warn};

use crate::backend::BackendClient;

const AUTH_METRICS_INTERVAL: Duration = Duration::from_secs(60);

#[tonic::async_trait]
trait ApiKeyValidator: Send + Sync {
    async fn validate_api_key(&self, api_key: &str) -> anyhow::Result<bool>;
}

#[tonic::async_trait]
impl ApiKeyValidator for BackendClient {
    async fn validate_api_key(&self, api_key: &str) -> anyhow::Result<bool> {
        BackendClient::validate_api_key(self, api_key).await
    }
}

#[derive(Debug, Clone, Copy)]
pub struct ApiKeyAuthConfig {
    pub positive_cache_ttl: Duration,
    pub positive_cache_max_entries: usize,
    pub max_concurrent_refreshes: usize,
    pub max_pending_requests: usize,
    pub validation_timeout: Duration,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RefreshFailure {
    BackendUnavailable,
    Timeout,
    Saturated,
    Cancelled,
}

type RefreshResult = Result<bool, RefreshFailure>;

#[derive(Debug)]
struct PositiveCacheEntry {
    expires_at: Instant,
    insertion_sequence: u64,
}

#[derive(Default)]
struct AuthState {
    positive_entries: HashMap<String, PositiveCacheEntry>,
    in_flight: HashMap<String, watch::Sender<Option<RefreshResult>>>,
    next_insertion_sequence: u64,
}

impl AuthState {
    fn is_valid_cached(&mut self, key: &str, now: Instant) -> bool {
        let Some(entry) = self.positive_entries.get(key) else {
            return false;
        };
        if entry.expires_at > now {
            return true;
        }
        self.positive_entries.remove(key);
        false
    }

    fn insert_positive(&mut self, key: String, now: Instant, ttl: Duration, max_entries: usize) {
        if ttl.is_zero() {
            return;
        }

        self.positive_entries
            .retain(|_, entry| entry.expires_at > now);

        if !self.positive_entries.contains_key(&key) && self.positive_entries.len() >= max_entries {
            let oldest_key = self
                .positive_entries
                .iter()
                .min_by_key(|(_, entry)| entry.insertion_sequence)
                .map(|(entry_key, _)| entry_key.clone());
            if let Some(oldest_key) = oldest_key {
                self.positive_entries.remove(&oldest_key);
            }
        }

        self.next_insertion_sequence = self.next_insertion_sequence.wrapping_add(1);
        self.positive_entries.insert(
            key,
            PositiveCacheEntry {
                expires_at: now + ttl,
                insertion_sequence: self.next_insertion_sequence,
            },
        );
    }
}

#[derive(Default)]
struct AuthMetrics {
    requests: AtomicU64,
    cache_hits: AtomicU64,
    cache_misses: AtomicU64,
    coalesced_waiters: AtomicU64,
    backend_validations: AtomicU64,
    backend_valid: AtomicU64,
    backend_invalid: AtomicU64,
    backend_unavailable: AtomicU64,
    validation_timeouts: AtomicU64,
    refresh_saturated: AtomicU64,
    pending_saturated: AtomicU64,
    backend_latency_micros_total: AtomicU64,
    backend_latency_micros_max: AtomicU64,
}

#[derive(Default)]
struct AuthMetricSnapshot {
    requests: u64,
    cache_hits: u64,
    cache_misses: u64,
    coalesced_waiters: u64,
    backend_validations: u64,
    backend_valid: u64,
    backend_invalid: u64,
    backend_unavailable: u64,
    validation_timeouts: u64,
    refresh_saturated: u64,
    pending_saturated: u64,
    backend_latency_micros_total: u64,
    backend_latency_micros_max: u64,
}

impl AuthMetrics {
    fn take_snapshot(&self) -> AuthMetricSnapshot {
        AuthMetricSnapshot {
            requests: self.requests.swap(0, Ordering::Relaxed),
            cache_hits: self.cache_hits.swap(0, Ordering::Relaxed),
            cache_misses: self.cache_misses.swap(0, Ordering::Relaxed),
            coalesced_waiters: self.coalesced_waiters.swap(0, Ordering::Relaxed),
            backend_validations: self.backend_validations.swap(0, Ordering::Relaxed),
            backend_valid: self.backend_valid.swap(0, Ordering::Relaxed),
            backend_invalid: self.backend_invalid.swap(0, Ordering::Relaxed),
            backend_unavailable: self.backend_unavailable.swap(0, Ordering::Relaxed),
            validation_timeouts: self.validation_timeouts.swap(0, Ordering::Relaxed),
            refresh_saturated: self.refresh_saturated.swap(0, Ordering::Relaxed),
            pending_saturated: self.pending_saturated.swap(0, Ordering::Relaxed),
            backend_latency_micros_total: self
                .backend_latency_micros_total
                .swap(0, Ordering::Relaxed),
            backend_latency_micros_max: self.backend_latency_micros_max.swap(0, Ordering::Relaxed),
        }
    }
}

struct ApiKeyAuthInner {
    backend: Arc<dyn ApiKeyValidator>,
    config: ApiKeyAuthConfig,
    state: Mutex<AuthState>,
    refresh_slots: Arc<Semaphore>,
    pending_slots: Arc<Semaphore>,
    metrics: AuthMetrics,
}

impl ApiKeyAuthInner {
    fn new(backend: Arc<dyn ApiKeyValidator>, config: ApiKeyAuthConfig) -> Arc<Self> {
        assert!(config.positive_cache_max_entries > 0);
        assert!(config.max_concurrent_refreshes > 0);
        assert!(config.max_pending_requests > 0);
        assert!(!config.validation_timeout.is_zero());

        Arc::new(Self {
            backend,
            config,
            state: Mutex::new(AuthState::default()),
            refresh_slots: Arc::new(Semaphore::new(config.max_concurrent_refreshes)),
            pending_slots: Arc::new(Semaphore::new(config.max_pending_requests)),
            metrics: AuthMetrics::default(),
        })
    }

    async fn is_valid_cached(&self, key: &str) -> bool {
        if self.config.positive_cache_ttl.is_zero() {
            return false;
        }
        self.state.lock().await.is_valid_cached(key, Instant::now())
    }

    async fn authoritative_refresh(&self, api_key: &str) -> RefreshResult {
        let Ok(_refresh_permit) = Arc::clone(&self.refresh_slots).try_acquire_owned() else {
            self.metrics
                .refresh_saturated
                .fetch_add(1, Ordering::Relaxed);
            return Err(RefreshFailure::Saturated);
        };

        self.metrics
            .backend_validations
            .fetch_add(1, Ordering::Relaxed);
        let started = Instant::now();
        let result = timeout(
            self.config.validation_timeout,
            self.backend.validate_api_key(api_key),
        )
        .await;
        let elapsed_micros = started.elapsed().as_micros().min(u64::MAX as u128) as u64;
        self.metrics
            .backend_latency_micros_total
            .fetch_add(elapsed_micros, Ordering::Relaxed);
        self.metrics
            .backend_latency_micros_max
            .fetch_max(elapsed_micros, Ordering::Relaxed);

        match result {
            Ok(Ok(true)) => {
                self.metrics.backend_valid.fetch_add(1, Ordering::Relaxed);
                Ok(true)
            }
            Ok(Ok(false)) => {
                self.metrics.backend_invalid.fetch_add(1, Ordering::Relaxed);
                Ok(false)
            }
            Ok(Err(error)) => {
                self.metrics
                    .backend_unavailable
                    .fetch_add(1, Ordering::Relaxed);
                debug!(%error, "Backend API key validation unavailable");
                Err(RefreshFailure::BackendUnavailable)
            }
            Err(_) => {
                self.metrics
                    .validation_timeouts
                    .fetch_add(1, Ordering::Relaxed);
                Err(RefreshFailure::Timeout)
            }
        }
    }

    fn spawn_refresh(self: &Arc<Self>, key: String, api_key: String) {
        let inner = Arc::clone(self);
        tokio::spawn(async move {
            let result = inner.authoritative_refresh(&api_key).await;
            let sender = {
                let mut state = inner.state.lock().await;
                let sender = state.in_flight.remove(&key);
                if result == Ok(true) {
                    state.insert_positive(
                        key,
                        Instant::now(),
                        inner.config.positive_cache_ttl,
                        inner.config.positive_cache_max_entries,
                    );
                }
                sender
            };

            if let Some(sender) = sender {
                let _ = sender.send(Some(result));
            }
        });
    }

    fn start_metrics_reporter(inner: &Arc<Self>) {
        let weak: Weak<Self> = Arc::downgrade(inner);
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(AUTH_METRICS_INTERVAL);
            interval.tick().await;
            loop {
                interval.tick().await;
                let Some(inner) = weak.upgrade() else {
                    return;
                };
                inner.report_metrics().await;
            }
        });
    }

    async fn report_metrics(&self) {
        let snapshot = self.metrics.take_snapshot();
        if snapshot.requests == 0 {
            return;
        }

        let mut state = self.state.lock().await;
        let now = Instant::now();
        state
            .positive_entries
            .retain(|_, entry| entry.expires_at > now);
        let cache_entries = state.positive_entries.len();
        let in_flight_refreshes = state.in_flight.len();
        drop(state);

        let backend_latency_mean_micros = snapshot
            .backend_latency_micros_total
            .checked_div(snapshot.backend_validations)
            .unwrap_or(0);
        let has_degradation = snapshot.backend_unavailable > 0
            || snapshot.validation_timeouts > 0
            || snapshot.refresh_saturated > 0
            || snapshot.pending_saturated > 0;

        if has_degradation {
            warn!(
                requests = snapshot.requests,
                cache_hits = snapshot.cache_hits,
                cache_misses = snapshot.cache_misses,
                coalesced_waiters = snapshot.coalesced_waiters,
                backend_validations = snapshot.backend_validations,
                backend_valid = snapshot.backend_valid,
                backend_invalid = snapshot.backend_invalid,
                backend_unavailable = snapshot.backend_unavailable,
                validation_timeouts = snapshot.validation_timeouts,
                refresh_saturated = snapshot.refresh_saturated,
                pending_saturated = snapshot.pending_saturated,
                backend_latency_mean_micros,
                backend_latency_max_micros = snapshot.backend_latency_micros_max,
                cache_entries,
                in_flight_refreshes,
                "API key authorization interval degraded"
            );
        } else {
            info!(
                requests = snapshot.requests,
                cache_hits = snapshot.cache_hits,
                cache_misses = snapshot.cache_misses,
                coalesced_waiters = snapshot.coalesced_waiters,
                backend_validations = snapshot.backend_validations,
                backend_valid = snapshot.backend_valid,
                backend_invalid = snapshot.backend_invalid,
                backend_latency_mean_micros,
                backend_latency_max_micros = snapshot.backend_latency_micros_max,
                cache_entries,
                in_flight_refreshes,
                "API key authorization interval"
            );
        }
    }
}

/// API key authentication delegated to the authoritative backend with a short,
/// fixed-TTL positive cache and coalesced same-key refreshes.
#[derive(Clone)]
pub struct ApiKeyInterceptor {
    inner: Arc<ApiKeyAuthInner>,
}

impl ApiKeyInterceptor {
    pub fn new(backend: Arc<BackendClient>, config: ApiKeyAuthConfig) -> Self {
        let inner = ApiKeyAuthInner::new(backend, config);
        ApiKeyAuthInner::start_metrics_reporter(&inner);
        Self { inner }
    }

    #[cfg(test)]
    fn with_validator(backend: Arc<dyn ApiKeyValidator>, config: ApiKeyAuthConfig) -> Self {
        Self {
            inner: ApiKeyAuthInner::new(backend, config),
        }
    }

    pub async fn validate(&self, api_key: &str) -> Result<bool, Status> {
        self.inner.metrics.requests.fetch_add(1, Ordering::Relaxed);

        if self.inner.is_valid_cached(api_key).await {
            self.inner
                .metrics
                .cache_hits
                .fetch_add(1, Ordering::Relaxed);
            return Ok(true);
        }

        let Ok(_pending_permit) = Arc::clone(&self.inner.pending_slots).try_acquire_owned() else {
            self.inner
                .metrics
                .pending_saturated
                .fetch_add(1, Ordering::Relaxed);
            return Err(Status::unavailable(
                "API key validation capacity temporarily exhausted",
            ));
        };

        let key = api_key.to_string();
        let (mut receiver, start_refresh) = {
            let mut state = self.inner.state.lock().await;
            if !self.inner.config.positive_cache_ttl.is_zero()
                && state.is_valid_cached(api_key, Instant::now())
            {
                self.inner
                    .metrics
                    .cache_hits
                    .fetch_add(1, Ordering::Relaxed);
                return Ok(true);
            }
            if let Some(sender) = state.in_flight.get(&key) {
                self.inner
                    .metrics
                    .coalesced_waiters
                    .fetch_add(1, Ordering::Relaxed);
                (sender.subscribe(), false)
            } else {
                let (sender, receiver) = watch::channel(None);
                state.in_flight.insert(key.clone(), sender);
                self.inner
                    .metrics
                    .cache_misses
                    .fetch_add(1, Ordering::Relaxed);
                (receiver, true)
            }
        };

        if start_refresh {
            self.inner.spawn_refresh(key, api_key.to_string());
        }

        let result = loop {
            let current = *receiver.borrow();
            if let Some(result) = current {
                break result;
            }
            if receiver.changed().await.is_err() {
                break Err(RefreshFailure::Cancelled);
            }
        };

        match result {
            Ok(is_valid) => Ok(is_valid),
            Err(
                RefreshFailure::BackendUnavailable
                | RefreshFailure::Timeout
                | RefreshFailure::Saturated
                | RefreshFailure::Cancelled,
            ) => Err(Status::unavailable(
                "API key validation service unavailable",
            )),
        }
    }

    /// Extract API key from request metadata.
    pub fn extract_api_key<T>(request: &Request<T>) -> Option<String> {
        request
            .metadata()
            .get("x-junjo-api-key")
            .and_then(|value| value.to_str().ok())
            .map(str::to_string)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::VecDeque;
    use std::sync::atomic::{AtomicBool, AtomicUsize};
    use std::sync::Mutex as StdMutex;
    use tokio::sync::Notify;

    fn config(ttl: Duration) -> ApiKeyAuthConfig {
        ApiKeyAuthConfig {
            positive_cache_ttl: ttl,
            positive_cache_max_entries: 1024,
            max_concurrent_refreshes: 8,
            max_pending_requests: 128,
            validation_timeout: Duration::from_secs(2),
        }
    }

    struct SequenceValidator {
        calls: AtomicUsize,
        results: StdMutex<VecDeque<anyhow::Result<bool>>>,
    }

    impl SequenceValidator {
        fn new(results: impl IntoIterator<Item = anyhow::Result<bool>>) -> Self {
            Self {
                calls: AtomicUsize::new(0),
                results: StdMutex::new(results.into_iter().collect()),
            }
        }
    }

    #[tonic::async_trait]
    impl ApiKeyValidator for SequenceValidator {
        async fn validate_api_key(&self, _api_key: &str) -> anyhow::Result<bool> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            self.results.lock().unwrap().pop_front().unwrap()
        }
    }

    struct BlockingValidator {
        calls: AtomicUsize,
        started: Notify,
        release: Notify,
        result: AtomicBool,
    }

    struct TimeoutThenValidValidator {
        calls: AtomicUsize,
    }

    struct MutableValidator {
        calls: AtomicUsize,
        result: AtomicBool,
    }

    #[tonic::async_trait]
    impl ApiKeyValidator for MutableValidator {
        async fn validate_api_key(&self, _api_key: &str) -> anyhow::Result<bool> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            Ok(self.result.load(Ordering::SeqCst))
        }
    }

    struct SnapshotBlockingValidator {
        calls: AtomicUsize,
        started: Notify,
        release: Notify,
        result: AtomicBool,
    }

    #[tonic::async_trait]
    impl ApiKeyValidator for SnapshotBlockingValidator {
        async fn validate_api_key(&self, _api_key: &str) -> anyhow::Result<bool> {
            let call = self.calls.fetch_add(1, Ordering::SeqCst);
            let authoritative_result = self.result.load(Ordering::SeqCst);
            if call == 0 {
                self.started.notify_waiters();
                self.release.notified().await;
            }
            Ok(authoritative_result)
        }
    }

    #[tonic::async_trait]
    impl ApiKeyValidator for TimeoutThenValidValidator {
        async fn validate_api_key(&self, _api_key: &str) -> anyhow::Result<bool> {
            let call = self.calls.fetch_add(1, Ordering::SeqCst);
            if call == 0 {
                std::future::pending::<()>().await;
            }
            Ok(true)
        }
    }

    impl BlockingValidator {
        fn new(result: bool) -> Self {
            Self {
                calls: AtomicUsize::new(0),
                started: Notify::new(),
                release: Notify::new(),
                result: AtomicBool::new(result),
            }
        }
    }

    #[tonic::async_trait]
    impl ApiKeyValidator for BlockingValidator {
        async fn validate_api_key(&self, _api_key: &str) -> anyhow::Result<bool> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            self.started.notify_waiters();
            self.release.notified().await;
            Ok(self.result.load(Ordering::SeqCst))
        }
    }

    #[tokio::test]
    async fn successful_validation_is_reused_until_fixed_expiry() {
        tokio::time::pause();
        let validator = Arc::new(SequenceValidator::new([Ok(true), Ok(false)]));
        let auth =
            ApiKeyInterceptor::with_validator(validator.clone(), config(Duration::from_secs(10)));

        assert!(auth.validate("fixed-expiry-key").await.unwrap());
        tokio::time::advance(Duration::from_secs(9)).await;
        assert!(auth.validate("fixed-expiry-key").await.unwrap());
        tokio::time::advance(Duration::from_secs(2)).await;
        assert!(!auth.validate("fixed-expiry-key").await.unwrap());
        assert_eq!(validator.calls.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn invalid_and_failed_results_are_not_cached() {
        let validator = Arc::new(SequenceValidator::new([
            Ok(false),
            Err(anyhow::anyhow!("backend unavailable")),
            Ok(true),
        ]));
        let auth =
            ApiKeyInterceptor::with_validator(validator.clone(), config(Duration::from_secs(10)));

        assert!(!auth.validate("uncached-result").await.unwrap());
        assert_eq!(
            auth.validate("uncached-result").await.unwrap_err().code(),
            tonic::Code::Unavailable
        );
        assert!(auth.validate("uncached-result").await.unwrap());
        assert_eq!(validator.calls.load(Ordering::SeqCst), 3);
    }

    #[tokio::test]
    async fn timeout_is_retryable_and_not_cached() {
        tokio::time::pause();
        let validator = Arc::new(TimeoutThenValidValidator {
            calls: AtomicUsize::new(0),
        });
        let mut test_config = config(Duration::from_secs(10));
        test_config.validation_timeout = Duration::from_secs(1);
        let auth = ApiKeyInterceptor::with_validator(validator.clone(), test_config);

        let timed_out = {
            let auth = auth.clone();
            tokio::spawn(async move { auth.validate("timeout-key").await })
        };
        while validator.calls.load(Ordering::SeqCst) == 0 {
            tokio::task::yield_now().await;
        }
        tokio::time::advance(Duration::from_secs(2)).await;
        assert_eq!(
            timed_out.await.unwrap().unwrap_err().code(),
            tonic::Code::Unavailable
        );

        assert!(auth.validate("timeout-key").await.unwrap());
        assert_eq!(validator.calls.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn expired_positive_is_not_served_when_refresh_fails() {
        tokio::time::pause();
        let validator = Arc::new(SequenceValidator::new([
            Ok(true),
            Err(anyhow::anyhow!("backend unavailable after expiry")),
        ]));
        let auth =
            ApiKeyInterceptor::with_validator(validator.clone(), config(Duration::from_secs(10)));

        assert!(auth.validate("no-stale-key").await.unwrap());
        tokio::time::advance(Duration::from_secs(11)).await;
        assert_eq!(
            auth.validate("no-stale-key").await.unwrap_err().code(),
            tonic::Code::Unavailable
        );
        assert_eq!(validator.calls.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn deletion_after_a_warm_hit_is_observed_at_fixed_expiry() {
        tokio::time::pause();
        let validator = Arc::new(MutableValidator {
            calls: AtomicUsize::new(0),
            result: AtomicBool::new(true),
        });
        let auth =
            ApiKeyInterceptor::with_validator(validator.clone(), config(Duration::from_secs(10)));

        assert!(auth.validate("deleted-key").await.unwrap());
        validator.result.store(false, Ordering::SeqCst);
        tokio::time::advance(Duration::from_secs(9)).await;
        assert!(auth.validate("deleted-key").await.unwrap());
        tokio::time::advance(Duration::from_secs(2)).await;
        assert!(!auth.validate("deleted-key").await.unwrap());
        assert_eq!(validator.calls.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn deletion_racing_after_authoritative_lookup_keeps_one_fixed_window() {
        tokio::time::pause();
        let validator = Arc::new(SnapshotBlockingValidator {
            calls: AtomicUsize::new(0),
            started: Notify::new(),
            release: Notify::new(),
            result: AtomicBool::new(true),
        });
        let auth =
            ApiKeyInterceptor::with_validator(validator.clone(), config(Duration::from_secs(10)));

        let in_flight = {
            let auth = auth.clone();
            tokio::spawn(async move { auth.validate("racing-deletion-key").await })
        };
        validator.started.notified().await;
        validator.result.store(false, Ordering::SeqCst);
        validator.release.notify_waiters();

        assert!(in_flight.await.unwrap().unwrap());
        tokio::time::advance(Duration::from_secs(11)).await;
        assert!(!auth.validate("racing-deletion-key").await.unwrap());
        assert_eq!(validator.calls.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn simultaneous_same_key_misses_are_coalesced() {
        let validator = Arc::new(BlockingValidator::new(true));
        let auth =
            ApiKeyInterceptor::with_validator(validator.clone(), config(Duration::from_secs(10)));

        let requests: Vec<_> = (0..100)
            .map(|_| {
                let auth = auth.clone();
                tokio::spawn(async move { auth.validate("shared-key").await })
            })
            .collect();

        validator.started.notified().await;
        for _ in 0..10 {
            tokio::task::yield_now().await;
        }
        validator.release.notify_waiters();

        for request in requests {
            assert!(request.await.unwrap().unwrap());
        }
        assert_eq!(validator.calls.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn cancelled_leader_does_not_cancel_shared_refresh() {
        let validator = Arc::new(BlockingValidator::new(true));
        let auth =
            ApiKeyInterceptor::with_validator(validator.clone(), config(Duration::from_secs(10)));

        let leader = {
            let auth = auth.clone();
            tokio::spawn(async move { auth.validate("cancel-safe-key").await })
        };
        validator.started.notified().await;
        leader.abort();

        let follower = {
            let auth = auth.clone();
            tokio::spawn(async move { auth.validate("cancel-safe-key").await })
        };
        tokio::task::yield_now().await;
        validator.release.notify_waiters();

        assert!(follower.await.unwrap().unwrap());
        assert_eq!(validator.calls.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn distinct_key_refreshes_are_bounded_without_queueing() {
        let validator = Arc::new(BlockingValidator::new(true));
        let mut test_config = config(Duration::from_secs(10));
        test_config.max_concurrent_refreshes = 1;
        let auth = ApiKeyInterceptor::with_validator(validator.clone(), test_config);

        let first = {
            let auth = auth.clone();
            tokio::spawn(async move { auth.validate("first-key").await })
        };
        validator.started.notified().await;

        let second_error = auth.validate("second-key").await.unwrap_err();
        assert_eq!(second_error.code(), tonic::Code::Unavailable);

        validator.release.notify_waiters();
        assert!(first.await.unwrap().unwrap());
        assert_eq!(validator.calls.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn pending_cold_requests_are_bounded() {
        let validator = Arc::new(BlockingValidator::new(true));
        let mut test_config = config(Duration::from_secs(10));
        test_config.max_pending_requests = 2;
        let auth = ApiKeyInterceptor::with_validator(validator.clone(), test_config);

        let first = {
            let auth = auth.clone();
            tokio::spawn(async move { auth.validate("pending-key").await })
        };
        validator.started.notified().await;
        let second = {
            let auth = auth.clone();
            tokio::spawn(async move { auth.validate("pending-key").await })
        };
        tokio::task::yield_now().await;

        let third_error = auth.validate("pending-key").await.unwrap_err();
        assert_eq!(third_error.code(), tonic::Code::Unavailable);

        validator.release.notify_waiters();
        assert!(first.await.unwrap().unwrap());
        assert!(second.await.unwrap().unwrap());
        assert_eq!(validator.calls.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn cache_capacity_evicts_the_oldest_validation() {
        let validator = Arc::new(SequenceValidator::new([
            Ok(true),
            Ok(true),
            Ok(true),
            Ok(true),
        ]));
        let mut test_config = config(Duration::from_secs(30));
        test_config.positive_cache_max_entries = 2;
        let auth = ApiKeyInterceptor::with_validator(validator.clone(), test_config);

        assert!(auth.validate("key-a").await.unwrap());
        assert!(auth.validate("key-b").await.unwrap());
        assert!(auth.validate("key-c").await.unwrap());
        assert!(auth.validate("key-a").await.unwrap());
        assert_eq!(validator.calls.load(Ordering::SeqCst), 4);
    }

    #[tokio::test]
    async fn zero_ttl_disables_positive_reuse() {
        let validator = Arc::new(SequenceValidator::new([Ok(true), Ok(false)]));
        let auth = ApiKeyInterceptor::with_validator(validator.clone(), config(Duration::ZERO));

        assert!(auth.validate("no-cache-key").await.unwrap());
        assert!(!auth.validate("no-cache-key").await.unwrap());
        assert_eq!(validator.calls.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn backend_outage_is_retryable_unavailable() {
        let backend = Arc::new(
            BackendClient::new(
                "http://127.0.0.1:1".to_string(),
                "test-internal-grpc-token-32-bytes-long".to_string(),
                Duration::from_millis(100),
            )
            .unwrap(),
        );
        let error = ApiKeyInterceptor::new(backend, config(Duration::from_secs(10)))
            .validate("valid-looking-key")
            .await
            .expect_err("an unreachable backend must fail validation transport");

        assert_eq!(error.code(), tonic::Code::Unavailable);
    }
}
