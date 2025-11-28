.PHONY: proto proto-check-orphans proto-clean proto-full-validation

# Uses shared proto directory at repo root
proto:
	protoc \
	-I../proto \
	--go_out=./proto_gen \
	--go-grpc_out=./proto_gen \
	../proto/*.proto

# Check for orphaned proto schemas (generated .pb.go files without source .proto files)
# This prevents schema orphaning where generated code exists but source proto is missing
proto-check-orphans:
	@echo "Verifying proto schemas..."
	@orphaned=0; \
	for pb_file in proto_gen/*.pb.go; do \
		if [ "$$pb_file" = "proto_gen/*.pb.go" ]; then break; fi; \
		source_path=$$(grep -m1 "^// source:" "$$pb_file" | sed 's|^// source: ||' | tr -d '[:space:]'); \
		if [ -z "$$source_path" ]; then continue; fi; \
		proto_file="../proto/$$source_path"; \
		if [ ! -f "$$proto_file" ]; then \
			echo "ERROR: Orphaned schema detected!"; \
			echo "  Generated: $$pb_file"; \
			echo "  Expected source: $$proto_file"; \
			echo "  (Referenced as: $$source_path in generated file)"; \
			orphaned=1; \
		fi; \
	done; \
	if [ $$orphaned -eq 1 ]; then \
		echo ""; \
		echo "FAILED: Some .pb.go files have missing .proto sources."; \
		echo "This usually happens when proto files are deleted during refactoring."; \
		echo "Either restore the .proto file or regenerate with 'make proto-clean && make proto'"; \
		exit 1; \
	fi; \
	echo "✓ All proto schemas verified"

# Clean generated proto files and regenerate from source
# Use this to ensure a clean state after proto refactoring
proto-clean:
	@echo "Cleaning generated proto files..."
	rm -f proto_gen/*.pb.go
	@echo "Regenerating proto files..."
	$(MAKE) proto
	@echo "✓ Proto files regenerated"

# Full proto validation pipeline: clean → regenerate → check for orphans
# Run this after proto refactoring to ensure everything is correct
proto-full-validation: proto-clean proto proto-check-orphans
	@echo "✓ Full proto validation complete"