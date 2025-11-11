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
	Store *storage.Storage
}

// NewWALReaderService creates a new WALReaderService.
func NewWALReaderService(store *storage.Storage) *WALReaderService {
	return &WALReaderService{Store: store}
}

// ReadSpans streams spans from the BadgerDB WAL to the client.
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

	err := s.Store.ReadSpans(req.StartKeyUlid, req.BatchSize, sendFunc)
	if err != nil {
		// Don't log EOF errors, as they are expected when a client disconnects.
		if err == io.EOF {
			slog.InfoContext(ctx, "client disconnected")
			return nil
		}
		slog.ErrorContext(ctx, "error reading spans from storage", slog.Any("error", err))
		return err
	}

	if spansStreamed == 0 {
		slog.DebugContext(ctx, "no spans found in storage", slog.String("start_key", string(req.StartKeyUlid)), slog.Int("batch_size", int(req.BatchSize)))
	} else {
		slog.InfoContext(ctx, "streamed spans", slog.Int("spans_streamed", int(spansStreamed)), slog.Int("batch_size", int(req.BatchSize)))
	}
	return nil
}
