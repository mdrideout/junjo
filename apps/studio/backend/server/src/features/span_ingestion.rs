//! Client for the ingestion service's internal gRPC API.
//!
//! The backend never receives span payloads over gRPC. It asks ingestion to
//! prepare a stable hot snapshot file and reads that file with DataFusion.

use std::time::Duration;

use tonic::Request;
use tonic::metadata::{Ascii, MetadataValue};
use tonic::transport::{Channel, Endpoint};

use crate::proto::internal_ingestion_service_client::InternalIngestionServiceClient;
use crate::proto::{FlushWalRequest, PrepareHotSnapshotRequest};

const INTERNAL_TOKEN_HEADER: &str = "x-junjo-internal-token";
/// Hard deadline for each internal RPC.
const RPC_TIMEOUT: Duration = Duration::from_secs(30);

/// What ingestion contributes to one query.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct IngestionQueryContext {
    /// A stable Parquet snapshot of unflushed spans. `None` means there is no
    /// hot tier to read for this query.
    pub hot_snapshot_path: Option<String>,
    /// Recently flushed cold files that the metadata index may not cover yet.
    pub recent_cold_paths: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct IngestionClient {
    client: InternalIngestionServiceClient<Channel>,
    token: MetadataValue<Ascii>,
}

impl IngestionClient {
    /// Create a client over one lazy, long-lived channel. The channel connects
    /// on first use and reconnects by itself after a failure.
    pub fn new(host: &str, port: u16, internal_token: &str) -> anyhow::Result<Self> {
        let endpoint = Endpoint::from_shared(format!("http://{host}:{port}"))?
            .http2_keep_alive_interval(Duration::from_secs(300))
            .keep_alive_timeout(Duration::from_secs(20))
            .keep_alive_while_idle(false);
        Ok(Self {
            client: InternalIngestionServiceClient::new(endpoint.connect_lazy()),
            token: internal_token.parse()?,
        })
    }

    /// Ask ingestion for the hot snapshot and the recent-cold bridge.
    ///
    /// A failed call degrades to cold-only data rather than failing the query.
    pub async fn query_context(&self) -> IngestionQueryContext {
        let mut request = Request::new(PrepareHotSnapshotRequest {});
        request.set_timeout(RPC_TIMEOUT);
        request
            .metadata_mut()
            .insert(INTERNAL_TOKEN_HEADER, self.token.clone());

        let response = match self.client.clone().prepare_hot_snapshot(request).await {
            Ok(response) => response.into_inner(),
            Err(status) => {
                tracing::warn!(
                    code = ?status.code(),
                    details = status.message(),
                    "PrepareHotSnapshot RPC failed, will use COLD only"
                );
                return IngestionQueryContext::default();
            }
        };
        if !response.success {
            tracing::warn!(error = %response.error_message, "hot snapshot preparation failed");
        }
        // A successful response can still mean "no data": an empty WAL has an
        // empty snapshot path.
        let has_hot_data =
            response.success && !response.snapshot_path.is_empty() && response.row_count > 0;
        IngestionQueryContext {
            hot_snapshot_path: has_hot_data.then_some(response.snapshot_path),
            recent_cold_paths: response.recent_cold_paths,
        }
    }

    /// Ask ingestion to flush its write-ahead log to cold Parquet now. It
    /// answers when the flush is complete.
    pub async fn flush_wal(&self) -> Result<(), String> {
        let mut request = Request::new(FlushWalRequest {});
        request.set_timeout(RPC_TIMEOUT);
        request
            .metadata_mut()
            .insert(INTERNAL_TOKEN_HEADER, self.token.clone());

        let response = self
            .client
            .clone()
            .flush_wal(request)
            .await
            .map_err(|status| format!("FlushWAL RPC failed: {status}"))?
            .into_inner();
        if response.success {
            Ok(())
        } else {
            Err(response.error_message)
        }
    }
}
