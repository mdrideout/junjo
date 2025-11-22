.PHONY: proto clean check-version

PROTO_SRC_DIR := ./src/junjo/telemetry/junjo_server/proto
PROTO_OUT_DIR := ./src/junjo/telemetry/junjo_server/proto_gen
REQUIRED_PROTOC_VERSION := 30.2

check-version:
	@echo "Checking protoc version..."
	@VERSION=$$(protoc --version 2>&1 | awk '{print $$2}'); \
	if [ "$$VERSION" != "$(REQUIRED_PROTOC_VERSION)" ]; then \
		echo "❌ Error: protoc version mismatch."; \
		echo "   Expected: libprotoc $(REQUIRED_PROTOC_VERSION)"; \
		echo "   Found:    libprotoc $$VERSION"; \
		echo "   Please ensure protoc v$(REQUIRED_PROTOC_VERSION) is installed and in your PATH (see PROTO_VERSIONS.md)."; \
		exit 1; \
	fi
	@echo "✅ Version check passed: libprotoc $(REQUIRED_PROTOC_VERSION)"

proto: check-version
	python -m grpc_tools.protoc \
		-I$(PROTO_SRC_DIR) \
		--python_out=$(PROTO_OUT_DIR) \
		--grpc_python_out=$(PROTO_OUT_DIR) \
		--pyi_out=$(PROTO_OUT_DIR) \
		$(PROTO_SRC_DIR)/*.proto

	# Post-process every _pb2_grpc.py file for relative imports.
	# Cross-platform sed command (works on both macOS and Linux)
	@for file in $(PROTO_OUT_DIR)/*_pb2_grpc.py; do \
		echo "Fixing imports in $$file"; \
		sed -i.bak 's/^import \(.*_pb2\) as \(.*\)/from . import \1 as \2/' $$file && rm -f $$file.bak; \
	done

clean:
	rm -rf $(PROTO_OUT_DIR)/*
