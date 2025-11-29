package storage

import (
	"encoding/json"
	"testing"

	commonpb "go.opentelemetry.io/proto/otlp/common/v1"
	resourcepb "go.opentelemetry.io/proto/otlp/resource/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
)

func TestConvertSpanDataToRecord(t *testing.T) {
	// Create test span with all fields populated
	span := &tracepb.Span{
		TraceId:           []byte{0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10},
		SpanId:            []byte{0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18},
		ParentSpanId:      []byte{0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28},
		Name:              "test-operation",
		Kind:              tracepb.Span_SPAN_KIND_SERVER,
		StartTimeUnixNano: 1700000000000000000,
		EndTimeUnixNano:   1700000001000000000,
		Attributes: []*commonpb.KeyValue{
			{Key: "http.method", Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: "GET"}}},
			{Key: "http.status_code", Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_IntValue{IntValue: 200}}},
		},
		Events: []*tracepb.Span_Event{
			{
				Name:         "event1",
				TimeUnixNano: 1700000000500000000,
				Attributes: []*commonpb.KeyValue{
					{Key: "message", Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: "test event"}}},
				},
			},
		},
		Status: &tracepb.Status{
			Code:    tracepb.Status_STATUS_CODE_OK,
			Message: "success",
		},
	}

	resource := &resourcepb.Resource{
		Attributes: []*commonpb.KeyValue{
			{Key: "service.name", Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: "test-service"}}},
			{Key: "service.version", Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: "1.0.0"}}},
		},
	}

	data := &SpanData{
		Span:     span,
		Resource: resource,
	}

	record := ConvertSpanDataToRecord(data)

	// Verify basic fields
	if record.SpanID != "1112131415161718" {
		t.Errorf("SpanID = %s, want 1112131415161718", record.SpanID)
	}
	if record.TraceID != "0102030405060708090a0b0c0d0e0f10" {
		t.Errorf("TraceID = %s, want 0102030405060708090a0b0c0d0e0f10", record.TraceID)
	}
	if record.ParentSpanID == nil || *record.ParentSpanID != "2122232425262728" {
		t.Errorf("ParentSpanID = %v, want 2122232425262728", record.ParentSpanID)
	}
	if record.ServiceName != "test-service" {
		t.Errorf("ServiceName = %s, want test-service", record.ServiceName)
	}
	if record.Name != "test-operation" {
		t.Errorf("Name = %s, want test-operation", record.Name)
	}
	if record.SpanKind != 2 { // SPAN_KIND_SERVER = 2
		t.Errorf("SpanKind = %d, want 2", record.SpanKind)
	}
	if record.StartTimeNanos != 1700000000000000000 {
		t.Errorf("StartTimeNanos = %d, want 1700000000000000000", record.StartTimeNanos)
	}
	if record.EndTimeNanos != 1700000001000000000 {
		t.Errorf("EndTimeNanos = %d, want 1700000001000000000", record.EndTimeNanos)
	}
	if record.DurationNanos != 1000000000 {
		t.Errorf("DurationNanos = %d, want 1000000000", record.DurationNanos)
	}
	if record.StatusCode != 1 { // STATUS_CODE_OK = 1
		t.Errorf("StatusCode = %d, want 1", record.StatusCode)
	}
	if record.StatusMessage == nil || *record.StatusMessage != "success" {
		t.Errorf("StatusMessage = %v, want success", record.StatusMessage)
	}

	// Verify JSON fields
	var attrs map[string]any
	if err := json.Unmarshal([]byte(record.Attributes), &attrs); err != nil {
		t.Fatalf("Failed to unmarshal attributes: %v", err)
	}
	if attrs["http.method"] != "GET" {
		t.Errorf("Attribute http.method = %v, want GET", attrs["http.method"])
	}
	if attrs["http.status_code"] != float64(200) { // JSON numbers are float64
		t.Errorf("Attribute http.status_code = %v, want 200", attrs["http.status_code"])
	}

	var events []map[string]any
	if err := json.Unmarshal([]byte(record.Events), &events); err != nil {
		t.Fatalf("Failed to unmarshal events: %v", err)
	}
	if len(events) != 1 {
		t.Fatalf("Expected 1 event, got %d", len(events))
	}
	if events[0]["name"] != "event1" {
		t.Errorf("Event name = %v, want event1", events[0]["name"])
	}

	var resourceAttrs map[string]any
	if err := json.Unmarshal([]byte(record.ResourceAttributes), &resourceAttrs); err != nil {
		t.Fatalf("Failed to unmarshal resource attributes: %v", err)
	}
	if resourceAttrs["service.name"] != "test-service" {
		t.Errorf("Resource attribute service.name = %v, want test-service", resourceAttrs["service.name"])
	}
}

func TestConvertSpanDataToRecord_RootSpan(t *testing.T) {
	// Root span has no parent
	span := &tracepb.Span{
		TraceId:           []byte{0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10},
		SpanId:            []byte{0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18},
		ParentSpanId:      nil, // No parent
		Name:              "root-operation",
		Kind:              tracepb.Span_SPAN_KIND_CLIENT,
		StartTimeUnixNano: 1700000000000000000,
		EndTimeUnixNano:   1700000002000000000,
	}

	resource := &resourcepb.Resource{
		Attributes: []*commonpb.KeyValue{
			{Key: "service.name", Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: "root-service"}}},
		},
	}

	data := &SpanData{
		Span:     span,
		Resource: resource,
	}

	record := ConvertSpanDataToRecord(data)

	if record.ParentSpanID != nil {
		t.Errorf("ParentSpanID should be nil for root span, got %v", *record.ParentSpanID)
	}
	if record.StatusMessage != nil {
		t.Errorf("StatusMessage should be nil when no status, got %v", *record.StatusMessage)
	}
	if record.DurationNanos != 2000000000 {
		t.Errorf("DurationNanos = %d, want 2000000000", record.DurationNanos)
	}
}

func TestConvertSpanDataToRecord_NoResource(t *testing.T) {
	span := &tracepb.Span{
		TraceId:           []byte{0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10},
		SpanId:            []byte{0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18},
		Name:              "no-resource-operation",
		StartTimeUnixNano: 1700000000000000000,
		EndTimeUnixNano:   1700000001000000000,
	}

	data := &SpanData{
		Span:     span,
		Resource: nil,
	}

	record := ConvertSpanDataToRecord(data)

	if record.ServiceName != "unknown" {
		t.Errorf("ServiceName should be 'unknown' when no resource, got %s", record.ServiceName)
	}
	if record.ResourceAttributes != "{}" {
		t.Errorf("ResourceAttributes should be '{}' when no resource, got %s", record.ResourceAttributes)
	}
}

func TestExtractServiceName(t *testing.T) {
	tests := []struct {
		name     string
		resource *resourcepb.Resource
		want     string
	}{
		{
			name:     "nil resource",
			resource: nil,
			want:     "unknown",
		},
		{
			name: "empty attributes",
			resource: &resourcepb.Resource{
				Attributes: []*commonpb.KeyValue{},
			},
			want: "unknown",
		},
		{
			name: "no service.name attribute",
			resource: &resourcepb.Resource{
				Attributes: []*commonpb.KeyValue{
					{Key: "other.attr", Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: "value"}}},
				},
			},
			want: "unknown",
		},
		{
			name: "has service.name",
			resource: &resourcepb.Resource{
				Attributes: []*commonpb.KeyValue{
					{Key: "service.name", Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: "my-service"}}},
				},
			},
			want: "my-service",
		},
		{
			name: "empty string service.name",
			resource: &resourcepb.Resource{
				Attributes: []*commonpb.KeyValue{
					{Key: "service.name", Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: ""}}},
				},
			},
			want: "unknown",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := extractServiceName(tt.resource)
			if got != tt.want {
				t.Errorf("extractServiceName() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestAnyValueToGo(t *testing.T) {
	tests := []struct {
		name  string
		value *commonpb.AnyValue
		want  any
	}{
		{
			name:  "nil value",
			value: nil,
			want:  nil,
		},
		{
			name:  "string value",
			value: &commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: "test"}},
			want:  "test",
		},
		{
			name:  "bool value",
			value: &commonpb.AnyValue{Value: &commonpb.AnyValue_BoolValue{BoolValue: true}},
			want:  true,
		},
		{
			name:  "int value",
			value: &commonpb.AnyValue{Value: &commonpb.AnyValue_IntValue{IntValue: 42}},
			want:  int64(42),
		},
		{
			name:  "double value",
			value: &commonpb.AnyValue{Value: &commonpb.AnyValue_DoubleValue{DoubleValue: 3.14}},
			want:  3.14,
		},
		{
			name:  "bytes value",
			value: &commonpb.AnyValue{Value: &commonpb.AnyValue_BytesValue{BytesValue: []byte{0xde, 0xad, 0xbe, 0xef}}},
			want:  "deadbeef",
		},
		{
			name: "array value",
			value: &commonpb.AnyValue{Value: &commonpb.AnyValue_ArrayValue{
				ArrayValue: &commonpb.ArrayValue{
					Values: []*commonpb.AnyValue{
						{Value: &commonpb.AnyValue_StringValue{StringValue: "a"}},
						{Value: &commonpb.AnyValue_StringValue{StringValue: "b"}},
					},
				},
			}},
			want: []any{"a", "b"},
		},
		{
			name: "kvlist value",
			value: &commonpb.AnyValue{Value: &commonpb.AnyValue_KvlistValue{
				KvlistValue: &commonpb.KeyValueList{
					Values: []*commonpb.KeyValue{
						{Key: "key1", Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: "val1"}}},
					},
				},
			}},
			want: map[string]any{"key1": "val1"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := anyValueToGo(tt.value)

			// For slices and maps, use JSON comparison
			switch expected := tt.want.(type) {
			case []any:
				gotSlice, ok := got.([]any)
				if !ok {
					t.Fatalf("Expected slice, got %T", got)
				}
				if len(gotSlice) != len(expected) {
					t.Errorf("len = %d, want %d", len(gotSlice), len(expected))
				}
				for i, v := range expected {
					if gotSlice[i] != v {
						t.Errorf("index %d = %v, want %v", i, gotSlice[i], v)
					}
				}
			case map[string]any:
				gotMap, ok := got.(map[string]any)
				if !ok {
					t.Fatalf("Expected map, got %T", got)
				}
				for k, v := range expected {
					if gotMap[k] != v {
						t.Errorf("key %s = %v, want %v", k, gotMap[k], v)
					}
				}
			default:
				if got != tt.want {
					t.Errorf("anyValueToGo() = %v (%T), want %v (%T)", got, got, tt.want, tt.want)
				}
			}
		})
	}
}

func TestKeyValuesToJSON(t *testing.T) {
	tests := []struct {
		name  string
		attrs []*commonpb.KeyValue
		want  string
	}{
		{
			name:  "nil attrs",
			attrs: nil,
			want:  "{}",
		},
		{
			name:  "empty attrs",
			attrs: []*commonpb.KeyValue{},
			want:  "{}",
		},
		{
			name: "single string attr",
			attrs: []*commonpb.KeyValue{
				{Key: "key", Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: "value"}}},
			},
			want: `{"key":"value"}`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := keyValuesToJSON(tt.attrs)
			if got != tt.want {
				t.Errorf("keyValuesToJSON() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestEventsToJSON(t *testing.T) {
	tests := []struct {
		name   string
		events []*tracepb.Span_Event
		want   string
	}{
		{
			name:   "nil events",
			events: nil,
			want:   "[]",
		},
		{
			name:   "empty events",
			events: []*tracepb.Span_Event{},
			want:   "[]",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := eventsToJSON(tt.events)
			if got != tt.want {
				t.Errorf("eventsToJSON() = %v, want %v", got, tt.want)
			}
		})
	}
}
