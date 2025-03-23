package telemetry

import (
	"context"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"time"

	db_duckdb "junjo-server/db_duckdb"

	"github.com/google/uuid"
	commonpb "go.opentelemetry.io/proto/otlp/common/v1" // Import the common package
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
)

// convertKind converts the integer kind to its string representation.
func convertKind(kind int32) string {
	switch kind {
	case 1: // OTLP SpanKind.SPAN_KIND_CLIENT
		return "CLIENT"
	case 2: // OTLP SpanKind.SPAN_KIND_SERVER
		return "SERVER"
	case 3: // OTLP SpanKind.SPAN_KIND_INTERNAL
		return "INTERNAL"
	case 4: // OTLP SpanKind.SPAN_KIND_PRODUCER
		return "PRODUCER"
	case 5: // OTLP SpanKind.SPAN_KIND_CONSUMER
		return "CONSUMER"
	default:
		return "UNSPECIFIED" // Handle unknown/unset kind
	}
}

// extractStringAttribute extracts a string attribute from a protobuf attributes slice.
func extractStringAttribute(attributes []*commonpb.KeyValue, key string) string {
	for _, attr := range attributes {
		if attr.Key == key {
			if stringValue, ok := attr.Value.Value.(*commonpb.AnyValue_StringValue); ok {
				return stringValue.StringValue
			}
		}
	}
	return ""
}

// extractJSONAttribute extracts a string-encoded JSON attribute.
func extractJSONAttribute(attributes []*commonpb.KeyValue, key string) string {
	for _, attr := range attributes {
		if attr.Key == key {
			if stringValue, ok := attr.Value.Value.(*commonpb.AnyValue_StringValue); ok {
				return stringValue.StringValue
			}
		}
	}
	return "{}" // Default to an empty JSON object
}

// convertAttributesToJson converts protobuf KeyValue attributes to a JSON string.
func convertAttributesToJson(attributes []*commonpb.KeyValue) (string, error) {
	attrMap := make(map[string]interface{})
	for _, attr := range attributes {
		switch v := attr.Value.Value.(type) {
		case *commonpb.AnyValue_StringValue:
			attrMap[attr.Key] = v.StringValue
		case *commonpb.AnyValue_IntValue:
			attrMap[attr.Key] = v.IntValue
		case *commonpb.AnyValue_DoubleValue:
			attrMap[attr.Key] = v.DoubleValue
		case *commonpb.AnyValue_BoolValue:
			attrMap[attr.Key] = v.BoolValue
		case *commonpb.AnyValue_ArrayValue:
			var arr []interface{}
			for _, item := range v.ArrayValue.Values {
				switch i := item.Value.(type) {
				case *commonpb.AnyValue_StringValue:
					arr = append(arr, i.StringValue)
				case *commonpb.AnyValue_IntValue:
					arr = append(arr, i.IntValue)
				case *commonpb.AnyValue_DoubleValue:
					arr = append(arr, i.DoubleValue)
				case *commonpb.AnyValue_BoolValue:
					arr = append(arr, i.BoolValue)
				default:
					log.Printf("Unsupported array element type in attribute %s", attr.Key)
				}
			}
			attrMap[attr.Key] = arr
		case *commonpb.AnyValue_KvlistValue:
			kvlistMap := make(map[string]interface{})
			for _, kv := range v.KvlistValue.Values {
				switch k := kv.Value.Value.(type) {
				case *commonpb.AnyValue_StringValue:
					kvlistMap[kv.Key] = k.StringValue
				case *commonpb.AnyValue_IntValue:
					kvlistMap[kv.Key] = k.IntValue
				case *commonpb.AnyValue_DoubleValue:
					kvlistMap[kv.Key] = k.DoubleValue
				case *commonpb.AnyValue_BoolValue:
					kvlistMap[kv.Key] = k.BoolValue
				default: // Added default case
					log.Printf("Unsupported kvlist element type in attribute %s", attr.Key)
				}
			}
			attrMap[attr.Key] = kvlistMap
		case *commonpb.AnyValue_BytesValue:
			attrMap[attr.Key] = hex.EncodeToString(v.BytesValue)
		default:
			log.Printf("Unsupported attribute type: %T for key: %s", v, attr.Key)
		}
	}

	jsonBytes, err := json.Marshal(attrMap)
	if err != nil {
		return "", err
	}
	return string(jsonBytes), nil
}

// convertEventsToJson converts protobuf events to JSON
func convertEventsToJson(events []*tracepb.Span_Event) (string, error) {
	eventList := []map[string]interface{}{}
	for _, event := range events {
		eventMap := make(map[string]interface{})
		eventMap["name"] = event.Name
		eventMap["timeUnixNano"] = event.TimeUnixNano
		eventMap["droppedAttributesCount"] = event.DroppedAttributesCount

		attributesJSON, err := convertAttributesToJson(event.Attributes)
		if err != nil {
			return "", fmt.Errorf("failed to marshal event attributes to JSON: %w", err)
		}
		eventMap["attributes"] = json.RawMessage(attributesJSON) // Use json.RawMessage

		eventList = append(eventList, eventMap)
	}

	jsonBytes, err := json.Marshal(eventList)
	if err != nil {
		return "", err
	}
	return string(jsonBytes), nil
}

// ProcessSpan processes a single OpenTelemetry span (protobuf).
func ProcessSpan(ctx context.Context, service_name string, span *tracepb.Span) error {
	db := db_duckdb.DB
	if db == nil {
		return fmt.Errorf("database connection is nil")
	}

	// 1. Encode IDs CORRECTLY
	traceID := hex.EncodeToString(span.TraceId)
	spanID := hex.EncodeToString(span.SpanId)

	// Handle potentially missing parent_span_id
	var parentSpanID sql.NullString
	if len(span.ParentSpanId) > 0 {
		parentSpanID = sql.NullString{String: hex.EncodeToString(span.ParentSpanId), Valid: true}
	} else {
		parentSpanID = sql.NullString{Valid: false}
	}

	// 2. Timestamps
	startTime := time.Unix(0, int64(span.StartTimeUnixNano)).UTC()
	endTime := time.Unix(0, int64(span.EndTimeUnixNano)).UTC()

	// 3. Standard Attributes
	kindStr := convertKind(int32(span.Kind))
	statusCode := ""
	statusMessage := ""
	if span.Status != nil {
		statusCode = span.Status.Code.String()
		statusMessage = span.Status.Message
	}

	// 4. Junjo Attributes that need dedicated columns
	junjoSpanType := extractStringAttribute(span.Attributes, "junjo.span_type")
	junjoParentID := extractStringAttribute(span.Attributes, "junjo.parent_id")
	junjoID := extractStringAttribute(span.Attributes, "junjo.id")

	workflowID := ""
	if junjoSpanType == "workflow" {
		workflowID = extractStringAttribute(span.Attributes, "junjo.id")
	}

	nodeID := ""
	if junjoSpanType == "node" {
		nodeID = extractStringAttribute(span.Attributes, "junjo.id")
	}

	// JSON Attributes that need dedicated columns
	junjoInitialState := "{}"
	junjoFinalState := "{}"
	junjoGraphStructure := "{}"
	if junjoSpanType == "workflow" {
		junjoInitialState = extractJSONAttribute(span.Attributes, "junjo.workflow.state.start")
		junjoFinalState = extractJSONAttribute(span.Attributes, "junjo.workflow.state.end")
		junjoGraphStructure = extractJSONAttribute(span.Attributes, "junjo.workflow.graph_structure")
	}

	// Filter out attributes_json elements that we are extracting to dedicated columns
	filteredAttributes := []*commonpb.KeyValue{}
	for _, attr := range span.Attributes {
		switch attr.Key {
		case "junjo.workflow_id", "node.id", "junjo.id", "junjo.parent_id", "junjo.span_type", "junjo.workflow.state.start", "junjo.workflow.state.end", "junjo.workflow.graph_structure":
			// Skip - in dedicated columns
		default:
			filteredAttributes = append(filteredAttributes, attr)
		}
	}

	attributesJSON, err := convertAttributesToJson(filteredAttributes)
	if err != nil {
		return fmt.Errorf("failed to marshal attributes to JSON: %w", err)
	}

	eventsJSON, err := convertEventsToJson(span.Events)
	if err != nil {
		return fmt.Errorf("failed to marshal events to JSON: %w", err)
	}

	// Handle potentially missing trace_state
	var traceState sql.NullString
	if span.TraceState != "" {
		traceState = sql.NullString{String: span.TraceState, Valid: true}
	} else {
		traceState = sql.NullString{Valid: false}
	}

	// Insert into `spans`
	spanInsertQuery := `
		INSERT INTO spans (
			trace_id, span_id, parent_span_id, service_name, name, kind, start_time, end_time,
			status_code, status_message, attributes_json, events_json, links_json,
			trace_flags, trace_state, junjo_id, junjo_parent_id, junjo_span_type,
			junjo_wf_state_start, junjo_wf_state_end, junjo_wf_graph_structure
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);`

	// log.Printf("Executing query: %s with parameters: %v", spanInsertQuery, []interface{}{
	// 	traceID, spanID, parentSpanID, service_name, span.Name, kindStr, startTime, endTime,
	// 	statusCode, statusMessage, attributesJSON, eventsJSON, "[]",
	// 	span.Flags, traceState, junjoServiceName, junjoID, junjoParentID, junjoSpanType,
	// 	junjoInitialState, junjoFinalState,
	// })

	_, err = db.ExecContext(ctx, spanInsertQuery,
		traceID, spanID, parentSpanID, service_name, span.Name, kindStr, startTime, endTime,
		statusCode, statusMessage, attributesJSON, eventsJSON, "[]",
		span.Flags, traceState, junjoID, junjoParentID, junjoSpanType,
		junjoInitialState, junjoFinalState, junjoGraphStructure,
	)
	if err != nil {
		return fmt.Errorf("failed to insert span into DuckDB: %w", err)
	}

	// Insert State Patches
	patchInsertQuery := `
		INSERT INTO state_patches (patch_id, service_name, trace_id, span_id, workflow_id, node_id, event_time, patch)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?);`

	for _, event := range span.Events {
		if event.Name == "set_state" {
			eventTime := time.Unix(0, int64(event.TimeUnixNano)).UTC()
			patchJSON := extractJSONAttribute(event.Attributes, "state_json_patch")
			patchID := uuid.NewString()
			workflowID := workflowID
			nodeID := nodeID
			_, err = db.ExecContext(ctx, patchInsertQuery, patchID, service_name, traceID, spanID, workflowID, nodeID, eventTime, patchJSON)
			if err != nil {
				log.Printf("Error inserting patch: %v", err)
			}
		}
	}

	return nil
}
