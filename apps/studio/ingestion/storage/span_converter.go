package storage

import (
	"encoding/hex"
	"encoding/json"

	commonpb "go.opentelemetry.io/proto/otlp/common/v1"
	resourcepb "go.opentelemetry.io/proto/otlp/resource/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
)

// ConvertSpanDataToRecord converts a SpanData to a SpanRecord for Parquet writing.
func ConvertSpanDataToRecord(data *SpanData) SpanRecord {
	span := data.Span
	resource := data.Resource

	record := SpanRecord{
		SpanID:             hexEncode(span.GetSpanId()),
		TraceID:            hexEncode(span.GetTraceId()),
		ServiceName:        extractServiceName(resource),
		Name:               span.GetName(),
		SpanKind:           int8(span.GetKind()),
		StartTimeNanos:     int64(span.GetStartTimeUnixNano()),
		EndTimeNanos:       int64(span.GetEndTimeUnixNano()),
		DurationNanos:      int64(span.GetEndTimeUnixNano()) - int64(span.GetStartTimeUnixNano()),
		StatusCode:         extractStatusCode(span.GetStatus()),
		Attributes:         keyValuesToJSON(span.GetAttributes()),
		Events:             eventsToJSON(span.GetEvents()),
		ResourceAttributes: keyValuesToJSON(resource.GetAttributes()),
	}

	// Handle nullable fields
	if len(span.GetParentSpanId()) > 0 {
		parentID := hexEncode(span.GetParentSpanId())
		record.ParentSpanID = &parentID
	}

	if span.GetStatus() != nil && span.GetStatus().GetMessage() != "" {
		msg := span.GetStatus().GetMessage()
		record.StatusMessage = &msg
	}

	return record
}

// hexEncode converts bytes to hex string.
func hexEncode(b []byte) string {
	return hex.EncodeToString(b)
}

// extractServiceName extracts the service.name attribute from a resource.
// Returns "unknown" if not found.
func extractServiceName(resource *resourcepb.Resource) string {
	if resource == nil {
		return "unknown"
	}
	for _, attr := range resource.GetAttributes() {
		if attr.GetKey() == "service.name" {
			if sv := attr.GetValue().GetStringValue(); sv != "" {
				return sv
			}
		}
	}
	return "unknown"
}

// extractStatusCode extracts the status code as int8.
func extractStatusCode(status *tracepb.Status) int8 {
	if status == nil {
		return 0 // UNSET
	}
	return int8(status.GetCode())
}

// keyValuesToJSON converts OTLP KeyValue slice to JSON string.
func keyValuesToJSON(attrs []*commonpb.KeyValue) string {
	if len(attrs) == 0 {
		return "{}"
	}

	m := make(map[string]any, len(attrs))
	for _, kv := range attrs {
		m[kv.GetKey()] = anyValueToGo(kv.GetValue())
	}

	b, err := json.Marshal(m)
	if err != nil {
		return "{}"
	}
	return string(b)
}

// anyValueToGo converts OTLP AnyValue to a Go value for JSON marshaling.
func anyValueToGo(v *commonpb.AnyValue) any {
	if v == nil {
		return nil
	}

	switch val := v.GetValue().(type) {
	case *commonpb.AnyValue_StringValue:
		return val.StringValue
	case *commonpb.AnyValue_BoolValue:
		return val.BoolValue
	case *commonpb.AnyValue_IntValue:
		return val.IntValue
	case *commonpb.AnyValue_DoubleValue:
		return val.DoubleValue
	case *commonpb.AnyValue_BytesValue:
		return hex.EncodeToString(val.BytesValue)
	case *commonpb.AnyValue_ArrayValue:
		if val.ArrayValue == nil {
			return nil
		}
		arr := make([]any, len(val.ArrayValue.Values))
		for i, elem := range val.ArrayValue.Values {
			arr[i] = anyValueToGo(elem)
		}
		return arr
	case *commonpb.AnyValue_KvlistValue:
		if val.KvlistValue == nil {
			return nil
		}
		m := make(map[string]any, len(val.KvlistValue.Values))
		for _, kv := range val.KvlistValue.Values {
			m[kv.GetKey()] = anyValueToGo(kv.GetValue())
		}
		return m
	default:
		return nil
	}
}

// eventsToJSON converts span events to JSON string.
func eventsToJSON(events []*tracepb.Span_Event) string {
	if len(events) == 0 {
		return "[]"
	}

	type eventJSON struct {
		Name       string         `json:"name"`
		TimeNanos  int64          `json:"timeUnixNano"`
		Attributes map[string]any `json:"attributes,omitempty"`
	}

	result := make([]eventJSON, len(events))
	for i, e := range events {
		attrs := make(map[string]any, len(e.GetAttributes()))
		for _, kv := range e.GetAttributes() {
			attrs[kv.GetKey()] = anyValueToGo(kv.GetValue())
		}
		result[i] = eventJSON{
			Name:       e.GetName(),
			TimeNanos:  int64(e.GetTimeUnixNano()),
			Attributes: attrs,
		}
	}

	b, err := json.Marshal(result)
	if err != nil {
		return "[]"
	}
	return string(b)
}
