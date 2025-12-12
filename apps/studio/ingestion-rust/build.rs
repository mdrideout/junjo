use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let proto_dir = PathBuf::from("proto");
    let out_dir = PathBuf::from("src/proto");

    // Create output directory if it doesn't exist
    std::fs::create_dir_all(&out_dir)?;

    // Configure tonic-prost-build
    tonic_prost_build::configure()
        .out_dir(&out_dir)
        .build_server(true)
        .build_client(true)
        // Compile OpenTelemetry protos
        .compile_protos(
            &[
                proto_dir.join("opentelemetry/proto/common/v1/common.proto"),
                proto_dir.join("opentelemetry/proto/resource/v1/resource.proto"),
                proto_dir.join("opentelemetry/proto/trace/v1/trace.proto"),
                proto_dir.join("opentelemetry/proto/collector/trace/v1/trace_service.proto"),
                // Internal service protos
                proto_dir.join("ingestion.proto"),
                proto_dir.join("auth.proto"),
                proto_dir.join("span_data_container.proto"),
            ],
            &[proto_dir],
        )?;

    // Rerun build if any proto files change
    println!("cargo:rerun-if-changed=proto/");

    Ok(())
}
