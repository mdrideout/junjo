package server

import (
	"io"
	pb "junjo-server/ingestion-service/proto_gen"
	"junjo-server/ingestion-service/storage"
	"log"
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
	log.Printf("Received ReadSpans request. StartKey: %x, BatchSize: %d", req.StartKeyUlid, req.BatchSize)

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
			log.Println("Client disconnected.")
			return nil
		}
		log.Printf("Error reading spans from storage: %v", err)
		return err
	}

	if spansStreamed == 0 {
		log.Printf("No spans found in storage for request. StartKey: %x, BatchSize: %d", req.StartKeyUlid, req.BatchSize)
	} else {
		log.Printf("Finished streaming %d spans of %d batch request size.", spansStreamed, req.BatchSize)
	}
	return nil
}
