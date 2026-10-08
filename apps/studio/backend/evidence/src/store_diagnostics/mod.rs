//! Store evidence shared by Workflow and Agent diagnostics: payload slots,
//! OTLP loss integrity, and independent Store replay.

pub mod integrity;
pub mod json_patch;
pub mod payloads;
pub mod reconstruction;
pub mod schemas;
