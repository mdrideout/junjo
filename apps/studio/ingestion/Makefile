.PHONY: proto

# Uses shared proto directory at repo root
proto:
	protoc \
	-I../proto \
	--go_out=./proto_gen \
	--go-grpc_out=./proto_gen \
	../proto/*.proto