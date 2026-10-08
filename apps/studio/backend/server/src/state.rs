//! Shared application state, cloned into every request.

use std::sync::Arc;

use crate::db::{ApplicationDb, Db};
use crate::features::auth::session_store::SqliteSessionStore;
use crate::features::config::ConfigResponse;
use crate::features::otel_spans::query::QueryEngine;
use crate::features::parquet_indexer::IndexerHandle;
use crate::features::span_ingestion::IngestionClient;
use crate::ui::Ui;

#[derive(Clone)]
pub struct AppState {
    /// `junjo.db`: canonical application data.
    pub application_db: ApplicationDb,
    /// `metadata.db`: the reader connection. The indexer thread owns the writer.
    pub metadata: Db,
    pub session_store: SqliteSessionStore,
    pub ingestion: IngestionClient,
    pub query: Arc<QueryEngine>,
    /// Asks the indexer thread, which owns the metadata writer, for work.
    pub indexer: IndexerHandle,
    /// What the configuration endpoint reports.
    pub deployment: Arc<ConfigResponse>,
    /// The built UI, when this process serves it. Without it the process
    /// serves the API only, as it does behind the Vite development server.
    pub ui: Option<Arc<Ui>>,
}
