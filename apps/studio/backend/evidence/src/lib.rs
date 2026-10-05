//! Pure evidence logic for Junjo AI Studio.
//!
//! Everything here is a function of span evidence that has already been
//! loaded: payload parsing, Store reconstruction, Agent and Workflow
//! diagnostics, and trace evidence assembly. The crate performs no I/O and
//! depends on nothing that does, so the compiler enforces that boundary.
//!
//! Evidence is untrusted. Malformed evidence becomes a diagnostic with a
//! stable code; it never becomes a panic or an invented value.

pub mod agent_diagnostics;
pub mod json;
pub mod spans;
pub mod store_diagnostics;
pub mod telemetry_contract;
pub mod timestamps;
pub mod trace_evidence;
pub mod workflow_diagnostics;
