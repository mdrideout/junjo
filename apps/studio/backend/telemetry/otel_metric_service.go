package telemetry

import (
	"context"
	"fmt"
	"sync"

	colmetricpb "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	metricpb "go.opentelemetry.io/proto/otlp/metrics/v1"
)

type otelMetricService struct {
	colmetricpb.UnimplementedMetricsServiceServer
	mu              sync.Mutex
	receivedMetrics []*metricpb.Metric
}

func (s *otelMetricService) Export(ctx context.Context, req *colmetricpb.ExportMetricsServiceRequest) (*colmetricpb.ExportMetricsServiceResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	for _, resourceMetrics := range req.ResourceMetrics {
		for _, scopeMetrics := range resourceMetrics.ScopeMetrics {
			for _, metric := range scopeMetrics.Metrics {
				s.receivedMetrics = append(s.receivedMetrics, metric)
				fmt.Printf("OTel Metric Service: Received Metric: %s\n", metric.Name)
			}
		}
	}
	return &colmetricpb.ExportMetricsServiceResponse{}, nil
}
