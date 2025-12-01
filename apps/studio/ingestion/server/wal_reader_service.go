package server

import (
	"context"
	"io"
	"log/slog"

	pb "junjo-ai-studio/ingestion/proto_gen"
	"junjo-ai-studio/ingestion/storage"

	"google.golang.org/grpc"
)

// WALReaderService implements the gRPC server for reading from the WAL.
type WALReaderService struct {
	pb.UnimplementedInternalIngestionServiceServer
	repo    storage.SpanRepository
	flusher *storage.Flusher
}

// NewWALReaderService creates a new WALReaderService.
func NewWALReaderService(repo storage.SpanRepository, flusher *storage.Flusher) *WALReaderService {
	return &WALReaderService{repo: repo, flusher: flusher}
}

// ReadSpans streams spans from the SQLite WAL to the client.
func (s *WALReaderService) ReadSpans(req *pb.ReadSpansRequest, stream pb.InternalIngestionService_ReadSpansServer) error {
	ctx := stream.Context()
	slog.DebugContext(ctx, "received readspans request", slog.String("start_key", string(req.StartKeyUlid)), slog.Int("batch_size", int(req.BatchSize)))

	var spansStreamed int32
	sendFunc := func(key, spanBytes, resourceBytes []byte) error {
		res := &pb.ReadSpansResponse{
			KeyUlid:       key,
			SpanBytes:     spanBytes,
			ResourceBytes: resourceBytes,
		}
		spansStreamed++
		return stream.Send(res)
	}

	lastKeyProcessed, corruptedCount, err := s.repo.ReadSpans(req.StartKeyUlid, req.BatchSize, sendFunc)
	if err != nil {
		// Don't log EOF errors, as they are expected when a client disconnects.
		if err == io.EOF {
			slog.InfoContext(ctx, "client disconnected")
			return nil
		}
		slog.ErrorContext(ctx, "error reading spans from storage", slog.Any("error", err))
		return err
	}

	// Calculate total spans processed (successful + corrupted)
	totalProcessed := uint32(spansStreamed) + corruptedCount

	// Decrement the counter by total consumed and get the remaining count
	var remainingCount uint64
	if totalProcessed > 0 {
		remainingCount, err = s.repo.DecrementAndGetCount(totalProcessed)
		if err != nil {
			slog.ErrorContext(ctx, "error decrementing span counter", slog.Any("error", err))
			// Continue anyway - this is a non-critical error
			remainingCount = 0
		}
	} else {
		// If no spans were processed at all, just get the current count
		remainingCount, err = s.repo.GetUnretrievedCount()
		if err != nil {
			slog.ErrorContext(ctx, "error getting unretrieved count", slog.Any("error", err))
			remainingCount = 0
		}
	}

	// Send a final message with the remaining count and last key processed
	// This allows the backend to advance past corrupted spans even if none were successfully sent
	finalRes := &pb.ReadSpansResponse{
		KeyUlid:        lastKeyProcessed, // Include last key so backend can advance cursor
		RemainingCount: remainingCount,
	}
	if err := stream.Send(finalRes); err != nil {
		slog.ErrorContext(ctx, "error sending final count message", slog.Any("error", err))
		return err
	}

	// Log results with corruption tracking
	if corruptedCount > 0 {
		slog.WarnContext(ctx, "batch contained corrupted spans",
			slog.Int("spans_streamed", int(spansStreamed)),
			slog.Uint64("corrupted_count", uint64(corruptedCount)),
			slog.Uint64("total_processed", uint64(totalProcessed)),
			slog.Int("batch_size", int(req.BatchSize)),
			slog.Uint64("remaining_count", remainingCount))
	} else if spansStreamed == 0 {
		slog.DebugContext(ctx, "no spans found in storage",
			slog.String("start_key", string(req.StartKeyUlid)),
			slog.Int("batch_size", int(req.BatchSize)),
			slog.Uint64("remaining_count", remainingCount))
	} else {
		slog.InfoContext(ctx, "streamed spans",
			slog.Int("spans_streamed", int(spansStreamed)),
			slog.Int("batch_size", int(req.BatchSize)),
			slog.Uint64("remaining_count", remainingCount))
	}
	return nil
}

// GetWALSpansByTraceId returns all spans in the WAL matching a trace ID.
// Used for fusion queries combining WAL and Parquet data.
func (s *WALReaderService) GetWALSpansByTraceId(req *pb.GetWALSpansByTraceIdRequest, stream grpc.ServerStreamingServer[pb.SpanData]) error {
	ctx := stream.Context()
	slog.DebugContext(ctx, "received GetWALSpansByTraceId request", slog.String("trace_id", req.TraceId))

	spans, err := s.repo.GetWALSpansByTraceID(req.TraceId)
	if err != nil {
		slog.ErrorContext(ctx, "error getting WAL spans by trace_id", slog.Any("error", err))
		return err
	}

	for _, spanData := range spans {
		pbSpan := convertStorageSpanDataToProto(spanData)
		if err := stream.Send(pbSpan); err != nil {
			if err == io.EOF {
				slog.InfoContext(ctx, "client disconnected during GetWALSpansByTraceId")
				return nil
			}
			slog.ErrorContext(ctx, "error sending span", slog.Any("error", err))
			return err
		}
	}

	slog.InfoContext(ctx, "streamed WAL spans for trace",
		slog.String("trace_id", req.TraceId),
		slog.Int("spans_count", len(spans)))

	return nil
}

// GetWALDistinctServiceNames returns all distinct service names currently in the WAL.
func (s *WALReaderService) GetWALDistinctServiceNames(ctx context.Context, req *pb.GetWALDistinctServiceNamesRequest) (*pb.GetWALDistinctServiceNamesResponse, error) {
	slog.DebugContext(ctx, "received GetWALDistinctServiceNames request")

	services, err := s.repo.GetDistinctServiceNames()
	if err != nil {
		slog.ErrorContext(ctx, "error getting distinct service names", slog.Any("error", err))
		return nil, err
	}

	slog.InfoContext(ctx, "returning WAL distinct service names", slog.Int("count", len(services)))

	return &pb.GetWALDistinctServiceNamesResponse{
		ServiceNames: services,
	}, nil
}

// GetWALRootSpans returns root spans (no parent) from the WAL for a service.
func (s *WALReaderService) GetWALRootSpans(req *pb.GetWALRootSpansRequest, stream grpc.ServerStreamingServer[pb.SpanData]) error {
	ctx := stream.Context()
	slog.DebugContext(ctx, "received GetWALRootSpans request",
		slog.String("service_name", req.ServiceName),
		slog.Int("limit", int(req.Limit)))

	limit := int(req.Limit)
	if limit <= 0 {
		limit = 500 // Default limit
	}

	spans, err := s.repo.GetRootSpans(req.ServiceName, limit)
	if err != nil {
		slog.ErrorContext(ctx, "error getting root spans", slog.Any("error", err))
		return err
	}

	for _, spanData := range spans {
		pbSpan := convertStorageSpanDataToProto(spanData)
		if err := stream.Send(pbSpan); err != nil {
			if err == io.EOF {
				slog.InfoContext(ctx, "client disconnected during GetWALRootSpans")
				return nil
			}
			slog.ErrorContext(ctx, "error sending root span", slog.Any("error", err))
			return err
		}
	}

	slog.InfoContext(ctx, "streamed root spans",
		slog.String("service_name", req.ServiceName),
		slog.Int("spans_count", len(spans)))

	return nil
}

// GetWALSpansByService returns all spans from the WAL for a service.
// Used for fusion queries combining WAL and Parquet data.
func (s *WALReaderService) GetWALSpansByService(req *pb.GetWALSpansByServiceRequest, stream grpc.ServerStreamingServer[pb.SpanData]) error {
	ctx := stream.Context()
	slog.DebugContext(ctx, "received GetWALSpansByService request",
		slog.String("service_name", req.ServiceName),
		slog.Int("limit", int(req.Limit)))

	limit := int(req.Limit)
	if limit <= 0 {
		limit = 500 // Default limit
	}

	spans, err := s.repo.GetSpansByService(req.ServiceName, limit)
	if err != nil {
		slog.ErrorContext(ctx, "error getting spans by service", slog.Any("error", err))
		return err
	}

	for _, spanData := range spans {
		pbSpan := convertStorageSpanDataToProto(spanData)
		if err := stream.Send(pbSpan); err != nil {
			if err == io.EOF {
				slog.InfoContext(ctx, "client disconnected during GetWALSpansByService")
				return nil
			}
			slog.ErrorContext(ctx, "error sending service span", slog.Any("error", err))
			return err
		}
	}

	slog.InfoContext(ctx, "streamed service spans",
		slog.String("service_name", req.ServiceName),
		slog.Int("spans_count", len(spans)))

	return nil
}

// GetWALWorkflowSpans returns workflow-type spans from the WAL for a service.
// Filters spans where junjo.span_type = 'workflow'.
func (s *WALReaderService) GetWALWorkflowSpans(req *pb.GetWALWorkflowSpansRequest, stream grpc.ServerStreamingServer[pb.SpanData]) error {
	ctx := stream.Context()
	slog.DebugContext(ctx, "received GetWALWorkflowSpans request",
		slog.String("service_name", req.ServiceName),
		slog.Int("limit", int(req.Limit)))

	limit := int(req.Limit)
	if limit <= 0 {
		limit = 500 // Default limit
	}

	spans, err := s.repo.GetWorkflowSpans(req.ServiceName, limit)
	if err != nil {
		slog.ErrorContext(ctx, "error getting workflow spans", slog.Any("error", err))
		return err
	}

	for _, spanData := range spans {
		pbSpan := convertStorageSpanDataToProto(spanData)
		if err := stream.Send(pbSpan); err != nil {
			if err == io.EOF {
				slog.InfoContext(ctx, "client disconnected during GetWALWorkflowSpans")
				return nil
			}
			slog.ErrorContext(ctx, "error sending workflow span", slog.Any("error", err))
			return err
		}
	}

	slog.InfoContext(ctx, "streamed workflow spans",
		slog.String("service_name", req.ServiceName),
		slog.Int("spans_count", len(spans)))

	return nil
}

// convertStorageSpanDataToProto converts a storage.SpanData to a pb.SpanData for gRPC responses.
func convertStorageSpanDataToProto(data *storage.SpanData) *pb.SpanData {
	span := data.Span
	resource := data.Resource

	// Use span converter helpers from storage package
	record := storage.ConvertSpanDataToRecord(data)

	pbSpan := &pb.SpanData{
		SpanId:                 record.SpanID,
		TraceId:                record.TraceID,
		ServiceName:            record.ServiceName,
		Name:                   record.Name,
		SpanKind:               int32(record.SpanKind),
		StartTimeUnixNano:      record.StartTimeNanos,
		EndTimeUnixNano:        record.EndTimeNanos,
		DurationNs:             record.DurationNanos,
		StatusCode:             int32(record.StatusCode),
		AttributesJson:         record.Attributes,
		EventsJson:             record.Events,
		ResourceAttributesJson: record.ResourceAttributes,
	}

	// Handle nullable fields
	if record.ParentSpanID != nil {
		pbSpan.ParentSpanId = *record.ParentSpanID
	}

	if record.StatusMessage != nil {
		pbSpan.StatusMessage = *record.StatusMessage
	}

	// Note: span and resource are available if we need direct access
	_ = span
	_ = resource

	return pbSpan
}

// FlushWAL triggers an immediate flush of WAL data to Parquet files.
func (s *WALReaderService) FlushWAL(ctx context.Context, req *pb.FlushWALRequest) (*pb.FlushWALResponse, error) {
	slog.InfoContext(ctx, "received FlushWAL request")

	if s.flusher == nil {
		slog.ErrorContext(ctx, "flusher not configured")
		return &pb.FlushWALResponse{
			Success:      false,
			ErrorMessage: "flusher not configured",
		}, nil
	}

	if err := s.flusher.Flush(); err != nil {
		slog.ErrorContext(ctx, "flush failed", slog.Any("error", err))
		return &pb.FlushWALResponse{
			Success:      false,
			ErrorMessage: err.Error(),
		}, nil
	}

	slog.InfoContext(ctx, "FlushWAL completed successfully")
	return &pb.FlushWALResponse{
		Success: true,
	}, nil
}
