# Missing Test Coverage Plan

This document outlines additional tests needed to improve security, reliability, and performance testing.

## 1. Security Tests

### 1.1 SQL Injection Protection
**File**: `tests/security/test_sql_injection.py`

#### Tests to add:
- `test_api_key_lookup_sql_injection` - Inject SQL in API key lookup
  - Input: `'; DROP TABLE api_keys; --`
  - Expected: Should be properly escaped, no DB modification

- `test_user_email_sql_injection` - Inject SQL in user email field
  - Input: `admin'--`, `' OR '1'='1`
  - Expected: No authentication bypass

- `test_span_query_sql_injection` - Inject SQL in trace ID/span ID queries
  - Input: `aaa' UNION SELECT * FROM users--`
  - Expected: Parameterized queries prevent injection

**Why important**: Prevents unauthorized database access and data exfiltration

---

### 1.2 XSS Protection
**File**: `tests/security/test_xss.py`

#### Tests to add:
- `test_api_key_name_xss` - Store malicious script in API key name
  - Input: `<script>alert('xss')</script>`
  - Expected: Stored safely, returned escaped in API responses

- `test_span_attributes_xss` - Store XSS in span attributes
  - Input: Attributes with `<img src=x onerror=alert(1)>`
  - Expected: JSON escaping prevents execution

**Why important**: Prevents stored XSS attacks in the observability UI

---

### 1.3 Authentication Bypass Attempts
**File**: `tests/security/test_auth_bypass.py`

#### Tests to add:
- `test_session_cookie_tampering` - Modify session cookie
  - Action: Change session cookie data
  - Expected: 401 Unauthorized

- `test_expired_session_rejection` - Use expired session
  - Action: Sign in, wait for expiration, make request
  - Expected: 401 Unauthorized

- `test_api_key_brute_force_protection` - Rapid invalid attempts
  - Action: 1000 requests with invalid API keys
  - Expected: Rate limiting or lockout (if implemented)

- `test_concurrent_session_invalidation` - Sign out from one session
  - Action: Sign in from 2 devices, sign out from one
  - Expected: Other session still valid OR both invalidated (define policy)

- `test_create_first_user_race_condition` - Multiple simultaneous first user creations
  - Action: 10 concurrent POST /users/create-first-user
  - Expected: Only 1 succeeds, others get 400

**Why important**: Prevents unauthorized access to protected resources

---

### 1.4 Authorization Tests
**File**: `tests/security/test_authorization.py`

#### Tests to add:
- `test_user_cannot_delete_other_users_keys` - Cross-user data access
  - Action: User A tries to delete User B's API key
  - Expected: 403 Forbidden (when multi-user support exists)

- `test_grpc_requires_valid_api_key` - gRPC auth enforcement
  - Action: gRPC call with invalid/missing API key
  - Expected: Rejection

**Why important**: Ensures users can only access their own resources

---

## 2. Concurrent Access Tests

### 2.1 API Key Race Conditions
**File**: `tests/concurrency/test_api_key_races.py`

#### Tests to add:
- `test_concurrent_api_key_creation` - Create 100 keys simultaneously
  - Action: 100 threads/async tasks creating keys
  - Expected: All 100 keys created with unique IDs and keys
  - Validates: Nanoid uniqueness under load, DB transaction isolation

- `test_concurrent_key_delete_and_read` - Delete while reading
  - Action: Thread 1 deletes key, Thread 2 reads same key
  - Expected: Thread 2 gets None or stale data (acceptable), no crash

- `test_concurrent_duplicate_key_prevention` - Force duplicate key scenario
  - Action: Mock nanoid to return same value, create 2 keys concurrently
  - Expected: One succeeds, one fails with unique constraint error

**Why important**: Ensures data integrity under concurrent load

---

### 2.2 Span Ingestion Race Conditions
**File**: `tests/concurrency/test_span_ingestion_races.py`

#### Tests to add:
- `test_concurrent_span_batch_ingestion` - 10 threads ingesting spans
  - Action: 10 threads each sending 100 spans
  - Expected: All 1000 spans inserted correctly, no duplicates

- `test_concurrent_same_span_ingestion` - Duplicate span ingestion
  - Action: 5 threads send same span (same trace_id/span_id)
  - Expected: Idempotent - only 1 span in DB (INSERT OR IGNORE)

- `test_concurrent_state_patch_ordering` - State patches from multiple nodes
  - Action: Multiple concurrent patches to same workflow state
  - Expected: All patches recorded with correct timestamps

**Why important**: Distributed systems send spans concurrently from multiple services

---

### 2.3 Session Management Races
**File**: `tests/concurrency/test_session_races.py`

#### Tests to add:
- `test_concurrent_sign_in_same_user` - 10 sign-ins for same user
  - Action: 10 concurrent POST /sign-in for user@example.com
  - Expected: All succeed, each gets valid session cookie

- `test_concurrent_sign_out_same_session` - Sign out from same session twice
  - Action: 2 threads sign out with same session cookie
  - Expected: Both succeed (idempotent) OR one gets 401

**Why important**: Real users may have multiple devices/tabs

---

## 3. Performance Tests

### 3.1 Large Span Batches
**File**: `tests/performance/test_large_batches.py`

#### Tests to add:
- `test_ingest_1000_spans_single_batch` - Large batch ingestion
  - Action: Send 1000 spans in single gRPC batch
  - Expected: Completes in <2 seconds, all spans inserted
  - Metrics: Latency, memory usage

- `test_ingest_10000_spans_sequential` - Sustained load
  - Action: Send 100 batches of 100 spans each
  - Expected: Consistent latency, no memory leaks

- `test_query_trace_with_1000_spans` - Large trace retrieval
  - Action: Query trace with 1000 spans
  - Expected: Returns in <500ms, pagination works

- `test_span_with_large_attributes` - 100KB attribute payload
  - Action: Span with massive attributes_json (100KB)
  - Expected: Ingests successfully, query works

**Why important**: Production systems generate high volume of telemetry

---

### 3.2 Cache Under Load
**File**: `tests/performance/test_cache_load.py`

#### Tests to add:
- `test_models_cache_concurrent_access` - 100 threads reading cache
  - Action: 100 threads calling get_models_for_provider("openai")
  - Expected: Cache hit, no duplicate API calls

- `test_cache_thundering_herd` - Cache expiration with load
  - Action: 100 threads request expired cache simultaneously
  - Expected: Only 1 API call (cache stampede prevention)

- `test_cache_invalidation_under_load` - Refresh while being read
  - Action: Thread 1 refreshes, Threads 2-100 read
  - Expected: No race conditions, consistent data

**Why important**: High-traffic endpoints will stress the cache

---

### 3.3 Database Performance
**File**: `tests/performance/test_database_load.py`

#### Tests to add:
- `test_query_10000_spans_pagination` - Large dataset pagination
  - Setup: Insert 10,000 spans
  - Action: Query with limit=100, iterate through all pages
  - Expected: Consistent query time (<50ms per page)

- `test_concurrent_database_writes` - 50 concurrent writes
  - Action: 50 threads inserting spans/API keys
  - Expected: No deadlocks, all succeed

**Why important**: Database is the bottleneck in most applications

---

## 4. Error Recovery Tests

### 4.1 Database Connection Failures
**File**: `tests/error_recovery/test_database_failures.py`

#### Tests to add:
- `test_database_connection_retry` - DB temporarily unavailable
  - Action: Mock DB connection failure, then recovery
  - Expected: Automatic retry succeeds (if implemented), or graceful error

- `test_partial_batch_failure` - Some spans fail to insert
  - Action: Send batch with 1 malformed span + 99 valid spans
  - Expected: Transaction rolls back OR 99 succeed (define behavior)

- `test_database_pool_exhaustion` - All connections in use
  - Action: Hold all DB connections, make another request
  - Expected: Timeout or queue, then succeed when released

- `test_sqlite_locked_database` - SQLITE_BUSY error
  - Action: Long-running transaction, concurrent write
  - Expected: Retry logic or clear error message

**Why important**: Network/DB issues are common in production

---

### 4.2 External API Failures
**File**: `tests/error_recovery/test_external_api_failures.py`

#### Tests to add:
- `test_openai_api_timeout` - OpenAI API times out
  - Action: Mock 30s timeout from OpenAI
  - Expected: Graceful timeout, return error to user

- `test_openai_api_rate_limit` - 429 rate limit response
  - Action: Mock 429 from OpenAI
  - Expected: Return user-friendly error (not 500)

- `test_anthropic_api_network_error` - Network failure
  - Action: Mock socket timeout
  - Expected: User sees "provider unavailable" error

- `test_gemini_malformed_response` - Invalid JSON response
  - Action: Mock broken JSON from Gemini
  - Expected: Parse error, graceful fallback

**Why important**: External APIs are unreliable

---

### 4.3 Partial System Failures
**File**: `tests/error_recovery/test_partial_failures.py`

#### Tests to add:
- `test_grpc_server_down_http_still_works` - gRPC offline
  - Action: Stop gRPC server, make HTTP requests
  - Expected: HTTP endpoints still functional

- `test_duckdb_corruption_detection` - Corrupted DuckDB file
  - Action: Corrupt DuckDB file, attempt query
  - Expected: Clear error message, suggestion to rebuild

- `test_span_ingestion_with_missing_fields` - Incomplete span
  - Action: Span missing required fields (e.g., no end_time)
  - Expected: Validation error OR default values inserted

**Why important**: Systems should degrade gracefully

---

## Implementation Priority

### High Priority (Implement First)
1. **Security - Auth bypass tests** (Critical for production)
2. **Concurrency - API key creation races** (Data integrity)
3. **Error Recovery - Database failures** (Common production issue)

### Medium Priority
4. **Performance - Large span batches** (Scalability)
5. **Security - SQL injection** (Already using ORMs, but validate)
6. **Concurrency - Span ingestion races** (Distributed systems)

### Low Priority (Nice to Have)
7. **Performance - Cache load tests** (Optimization)
8. **Security - XSS** (Frontend responsibility, but defense in depth)
9. **Error Recovery - External API failures** (Can add incrementally)

---

## Testing Tools & Frameworks

### Concurrency Testing
```python
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

# Use pytest-xdist for parallel test execution
# Use asyncio.gather() for async concurrency
# Use ThreadPoolExecutor for sync concurrency
```

### Performance Testing
```python
import time
import psutil  # Memory profiling
import cProfile  # CPU profiling

# Consider: pytest-benchmark, locust for load testing
```

### Security Testing
```python
# Input validation with known attack patterns
# Use: owasp-testing-guide payloads
```

---

## Test Execution Strategy

### Local Development
- Run unit + integration tests: `pytest -m "unit or integration"`
- Skip slow tests: `pytest -m "not slow"`

### CI/CD Pipeline
- **Pull Requests**: Unit + Integration + Security (fast tests)
- **Nightly Builds**: + Concurrency + Performance (slow tests)
- **Pre-Release**: Full suite including load tests

### Test Markers
```python
@pytest.mark.security
@pytest.mark.concurrency
@pytest.mark.performance
@pytest.mark.slow  # >1 second
```

---

## Success Metrics

- **Security**: 0 vulnerabilities in OWASP Top 10 categories
- **Concurrency**: 1000 concurrent requests without data corruption
- **Performance**:
  - 1000 spans/batch in <2s
  - 99th percentile API latency <200ms
- **Error Recovery**: System auto-recovers from 90% of transient failures

---

## Notes

- Start with integration tests, add unit tests for complex failure scenarios
- Use mocking sparingly - prefer real database/system tests
- Document expected behavior for edge cases (e.g., duplicate span ingestion)
- Add test coverage reports: `pytest --cov=app --cov-report=html`
