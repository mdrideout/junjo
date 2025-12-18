fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Compile the internal ingestion service proto
    tonic_prost_build::compile_protos("proto/ingestion.proto")?;

    println!("cargo:rerun-if-changed=proto/ingestion.proto");
    Ok(())
}
