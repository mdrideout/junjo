.PHONY: proto clean

PROTO_SRC_DIR := ./src/junjo/telemetry/junjo_server/proto
PROTO_OUT_DIR := ./src/junjo/telemetry/junjo_server/proto_gen

proto:
	python -m grpc_tools.protoc \
		-I$(PROTO_SRC_DIR) \
		--python_out=$(PROTO_OUT_DIR) \
		--grpc_python_out=$(PROTO_OUT_DIR) \
		--pyi_out=$(PROTO_OUT_DIR) \
		$(PROTO_SRC_DIR)/*.proto

	# Post-process every _pb2_grpc.py file for relative imports.
	# Adjust the sed -i option as needed for your OS.
	@for file in $(PROTO_OUT_DIR)/*_pb2_grpc.py; do \
		echo "Fixing imports in $$file"; \
		sed -i '' 's/^import \(.*_pb2\) as \(.*\)/from . import \1 as \2/' $$file; \
	done

clean:
	rm -rf $(PROTO_OUT_DIR)/*
