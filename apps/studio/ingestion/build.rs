fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Compile protos from shared proto directory (parent of ingestion/)
    // This ensures the Rust service uses the same proto definitions as Python backend
    //
    // Both proto files use `package ingestion;` so they merge into a single module:
    // - ingestion.proto: InternalIngestionService (PrepareHotSnapshot, FlushWAL)
    // - auth.proto: InternalAuthService (ValidateApiKey)

    tonic_prost_build::configure().compile_protos(
        &["../proto/ingestion.proto", "../proto/auth.proto"],
        &["../proto"],
    )?;

    println!("cargo:rerun-if-changed=../proto/ingestion.proto");
    println!("cargo:rerun-if-changed=../proto/auth.proto");
    Ok(())
}
