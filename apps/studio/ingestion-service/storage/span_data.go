package storage

import (
	"fmt"

	containerpb "junjo-server/ingestion-service/proto_gen"

	resourcepb "go.opentelemetry.io/proto/otlp/resource/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/protobuf/proto"
)

// SpanData is a container for a span and its associated resource.
// This is what we'll store in BadgerDB.
type SpanData struct {
	Span     *tracepb.Span
	Resource *resourcepb.Resource
}

// MarshalSpanData serializes the SpanData struct into a single byte slice.
func MarshalSpanData(data *SpanData) ([]byte, error) {
	// Marshal the span and resource separately
	spanBytes, err := proto.Marshal(data.Span)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal span: %w", err)
	}
	resourceBytes, err := proto.Marshal(data.Resource)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal resource: %w", err)
	}

	// Wrap them in our custom container message
	container := &containerpb.SpanDataContainer{
		SpanBytes:     spanBytes,
		ResourceBytes: resourceBytes,
	}

	// Marshal the container
	return proto.Marshal(container)
}

// UnmarshalSpanData deserializes a byte slice back into a SpanData struct.
func UnmarshalSpanData(data []byte) (*SpanData, error) {
	// Unmarshal the container
	var container containerpb.SpanDataContainer
	if err := proto.Unmarshal(data, &container); err != nil {
		return nil, fmt.Errorf("failed to unmarshal span data container: %w", err)
	}

	// Unmarshal the span and resource
	var span tracepb.Span
	if err := proto.Unmarshal(container.SpanBytes, &span); err != nil {
		return nil, fmt.Errorf("failed to unmarshal span: %w", err)
	}
	var resource resourcepb.Resource
	// If there is no resource data, we'll just leave the resource as an empty struct
	if len(container.ResourceBytes) > 0 {
		if err := proto.Unmarshal(container.ResourceBytes, &resource); err != nil {
			return nil, fmt.Errorf("failed to unmarshal resource: %w", err)
		}
	}

	return &SpanData{
		Span:     &span,
		Resource: &resource,
	}, nil
}
