fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Compile the shared Studio protos. Both files use `package ingestion;`
    // so they merge into one generated module:
    // - auth.proto: InternalAuthService (ValidateApiKey), served here
    // - ingestion.proto: InternalIngestionService, called here
    tonic_prost_build::configure().compile_protos(
        &["../../proto/ingestion.proto", "../../proto/auth.proto"],
        &["../../proto"],
    )?;

    println!("cargo:rerun-if-changed=../../proto/ingestion.proto");
    println!("cargo:rerun-if-changed=../../proto/auth.proto");
    Ok(())
}
