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

// GetWALSpansArrow returns spans from WAL as Arrow IPC bytes.
// Supports filtering by trace_id, service_name, root_only, and workflow_only.
// Used for unified DataFusion queries combining WAL and Parquet data.
func (s *WALReaderService) GetWALSpansArrow(req *pb.GetWALSpansArrowRequest, stream grpc.ServerStreamingServer[pb.ArrowBatch]) error {
	ctx := stream.Context()

	// Build filter from request
	filter := storage.SpanFilter{
		RootOnly:     req.RootOnly,
		WorkflowOnly: req.WorkflowOnly,
		Limit:        int(req.Limit),
	}

	// Handle optional fields
	if req.TraceId != nil {
		filter.TraceID = *req.TraceId
	}
	if req.ServiceName != nil {
		filter.ServiceName = *req.ServiceName
	}

	slog.DebugContext(ctx, "received GetWALSpansArrow request",
		slog.String("trace_id", filter.TraceID),
		slog.String("service_name", filter.ServiceName),
		slog.Bool("root_only", filter.RootOnly),
		slog.Bool("workflow_only", filter.WorkflowOnly),
		slog.Int("limit", filter.Limit))

	// Query spans as SpanRecords
	records, err := s.repo.GetSpansFiltered(filter)
	if err != nil {
		slog.ErrorContext(ctx, "error getting filtered spans", slog.Any("error", err))
		return err
	}

	// Convert to Arrow IPC bytes
	ipcBytes, err := storage.SpanRecordsToIPCBytes(records)
	if err != nil {
		slog.ErrorContext(ctx, "error serializing to Arrow IPC", slog.Any("error", err))
		return err
	}

	// Send as a single batch (could be chunked for very large results)
	batch := &pb.ArrowBatch{
		IpcBytes: ipcBytes,
		RowCount: int32(len(records)),
		IsLast:   true,
	}

	if err := stream.Send(batch); err != nil {
		if err == io.EOF {
			slog.InfoContext(ctx, "client disconnected during GetWALSpansArrow")
			return nil
		}
		slog.ErrorContext(ctx, "error sending Arrow batch", slog.Any("error", err))
		return err
	}

	slog.InfoContext(ctx, "streamed WAL spans as Arrow IPC",
		slog.String("trace_id", filter.TraceID),
		slog.String("service_name", filter.ServiceName),
		slog.Int("row_count", len(records)),
		slog.Int("ipc_bytes", len(ipcBytes)))

	return nil
}

// GetHotSpansArrow returns only HOT tier spans (since last warm snapshot) as Arrow IPC bytes.
// This is the three-tier architecture query that returns only the newest data.
func (s *WALReaderService) GetHotSpansArrow(req *pb.GetHotSpansArrowRequest, stream grpc.ServerStreamingServer[pb.ArrowBatch]) error {
	ctx := stream.Context()

	// Build filter from request
	filter := storage.SpanFilter{
		RootOnly:     req.RootOnly,
		WorkflowOnly: req.WorkflowOnly,
		Limit:        int(req.Limit),
	}

	// Handle optional fields
	if req.TraceId != nil {
		filter.TraceID = *req.TraceId
	}
	if req.ServiceName != nil {
		filter.ServiceName = *req.ServiceName
	}

	// Get since_warm_ulid (may be nil for first query or after cold flush)
	var sinceWarmULID []byte
	if req.SinceWarmUlid != nil && len(req.SinceWarmUlid) > 0 {
		sinceWarmULID = req.SinceWarmUlid
	}

	slog.DebugContext(ctx, "received GetHotSpansArrow request",
		slog.String("trace_id", filter.TraceID),
		slog.String("service_name", filter.ServiceName),
		slog.Bool("root_only", filter.RootOnly),
		slog.Bool("workflow_only", filter.WorkflowOnly),
		slog.Int("limit", filter.Limit),
		slog.Bool("has_since_ulid", sinceWarmULID != nil))

	// Query spans since warm ULID
	records, _, err := s.repo.GetSpansSinceWarmULID(sinceWarmULID, filter)
	if err != nil {
		slog.ErrorContext(ctx, "error getting hot spans", slog.Any("error", err))
		return err
	}

	// Convert to Arrow IPC bytes
	ipcBytes, err := storage.SpanRecordsToIPCBytes(records)
	if err != nil {
		slog.ErrorContext(ctx, "error serializing to Arrow IPC", slog.Any("error", err))
		return err
	}

	// Send as a single batch
	batch := &pb.ArrowBatch{
		IpcBytes: ipcBytes,
		RowCount: int32(len(records)),
		IsLast:   true,
	}

	if err := stream.Send(batch); err != nil {
		if err == io.EOF {
			slog.InfoContext(ctx, "client disconnected during GetHotSpansArrow")
			return nil
		}
		slog.ErrorContext(ctx, "error sending Arrow batch", slog.Any("error", err))
		return err
	}

	slog.InfoContext(ctx, "streamed HOT spans as Arrow IPC",
		slog.String("trace_id", filter.TraceID),
		slog.String("service_name", filter.ServiceName),
		slog.Int("row_count", len(records)),
		slog.Int("ipc_bytes", len(ipcBytes)))

	return nil
}

// GetWarmCursor returns the current warm snapshot cursor state.
// Used by Python to know what's in warm tier vs hot tier.
func (s *WALReaderService) GetWarmCursor(ctx context.Context, req *pb.GetWarmCursorRequest) (*pb.GetWarmCursorResponse, error) {
	slog.DebugContext(ctx, "received GetWarmCursor request")

	state, err := s.repo.GetWarmSnapshotState()
	if err != nil {
		slog.ErrorContext(ctx, "error getting warm snapshot state", slog.Any("error", err))
		return nil, err
	}

	slog.DebugContext(ctx, "returning warm cursor",
		slog.Bool("has_ulid", state.LastWarmULID != nil),
		slog.Int64("last_warm_time_ns", state.LastWarmTimeNS),
		slog.Int("warm_file_count", state.WarmFileCount))

	return &pb.GetWarmCursorResponse{
		LastWarmUlid:   state.LastWarmULID,
		LastWarmTimeNs: state.LastWarmTimeNS,
		WarmFileCount:  int32(state.WarmFileCount),
	}, nil
}

// GetWALDistinctServiceNames returns all distinct service names currently in the WAL.
// DEPRECATED: Use GetHotSpansArrow + DataFusion instead.
func (s *WALReaderService) GetWALDistinctServiceNames(ctx context.Context, req *pb.GetWALDistinctServiceNamesRequest) (*pb.GetWALDistinctServiceNamesResponse, error) {
	slog.DebugContext(ctx, "received GetWALDistinctServiceNames request (DEPRECATED)")

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
