package ingestion_client

import (
	"context"
	"io"

	pb "junjo-server/proto_gen"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// SpanWithResource holds a span and its associated resource.
type SpanWithResource struct {
	KeyUlid       []byte
	SpanBytes     []byte
	ResourceBytes []byte
}

// Client provides a client for the internal ingestion service.
type Client struct {
	conn   *grpc.ClientConn
	client pb.InternalIngestionServiceClient
}

// NewClient creates a new gRPC client for the ingestion service.
func NewClient() (*Client, error) {
	addr := "ingestion-service:50052"

	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, err
	}

	return &Client{
		conn:   conn,
		client: pb.NewInternalIngestionServiceClient(conn),
	}, nil
}

// Close closes the gRPC connection.
func (c *Client) Close() {
	if c.conn != nil {
		c.conn.Close()
	}
}

// ReadSpans reads a batch of spans from the ingestion service.
func (c *Client) ReadSpans(ctx context.Context, startKey []byte, batchSize uint32) ([]*SpanWithResource, error) {
	req := &pb.ReadSpansRequest{
		StartKeyUlid: startKey,
		BatchSize:    batchSize,
	}

	stream, err := c.client.ReadSpans(ctx, req)
	if err != nil {
		return nil, err
	}

	var spans []*SpanWithResource
	for {
		res, err := stream.Recv()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}
		spans = append(spans, &SpanWithResource{
			KeyUlid:       res.KeyUlid,
			SpanBytes:     res.SpanBytes,
			ResourceBytes: res.ResourceBytes,
		})
	}

	return spans, nil
}
