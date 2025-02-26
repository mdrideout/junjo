.PHONY: proto

proto:
	protoc \
	--go_out=./proto_gen \
	--go_opt=paths=source_relative \
	--go-grpc_out=./proto_gen \
	--go-grpc_opt=paths=source_relative \
	./proto/*.proto