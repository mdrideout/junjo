package server

import (
	"io"
	"log/slog"

	pb "junjo-ai-studio/ingestion/proto_gen"
	"junjo-ai-studio/ingestion/storage"
)

// WALReaderService implements the gRPC server for reading from the WAL.
type WALReaderService struct {
	pb.UnimplementedInternalIngestionServiceServer
	repo storage.SpanRepository
}

// NewWALReaderService creates a new WALReaderService.
func NewWALReaderService(repo storage.SpanRepository) *WALReaderService {
	return &WALReaderService{repo: repo}
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
