//! The shared RFC 8785 identity vectors every telemetry consumer must agree
//! on.

mod common;

use junjo_evidence::agent_diagnostics::contract::{canonical_json, structural_fingerprint};

#[test]
fn structural_fingerprint_vectors_are_reproduced() {
    let vectors =
        common::read_json(&common::fixture_root().join("fingerprints/agent-structural-v1.json"));
    let vectors = vectors["vectors"].as_array().expect("fingerprint vectors");
    assert!(!vectors.is_empty());
    for vector in vectors {
        let name = &vector["name"];
        let canonical = canonical_json(&vector["material"]).unwrap();
        assert_eq!(
            String::from_utf8(canonical).unwrap(),
            vector["canonical"].as_str().unwrap(),
            "{name} canonical form"
        );
        let fingerprint =
            structural_fingerprint(vector["kind"].as_str().unwrap(), &vector["material"]).unwrap();
        assert_eq!(
            fingerprint,
            vector["structural_id"].as_str().unwrap(),
            "{name}"
        );
    }
}
