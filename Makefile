.PHONY: proto clean

PROTO_SRC_DIR := ./src/junjo/telemetry/junjo_ui/proto
PROTO_OUT_DIR := ./src/junjo/telemetry/junjo_ui/proto_gen

proto:
	python -m grpc_tools.protoc \
		-I$(PROTO_SRC_DIR) \
		--python_out=$(PROTO_OUT_DIR) \
		--grpc_python_out=$(PROTO_OUT_DIR) \
		--pyi_out=$(PROTO_OUT_DIR) \
		$(PROTO_SRC_DIR)/*.proto

	# Post-process the generated workflow_pb2_grpc.py for relative imports
	# (Example using sed on macOS — note the slightly different -i syntax on Linux vs Mac)
	sed -i '' 's#import workflow_pb2 as workflow__pb2#from . import workflow_pb2 as workflow__pb2#' \
		$(PROTO_OUT_DIR)/workflow_pb2_grpc.py

clean:
	rm -rf $(PROTO_OUT_DIR)/*
