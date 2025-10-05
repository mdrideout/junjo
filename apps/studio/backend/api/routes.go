package api

import (
	"junjo-server/api/llm"
	otel "junjo-server/api/otel"

	"github.com/labstack/echo/v4"
)

func InitRoutes(e *echo.Echo) {
	e.GET("/otel/span-service-names", otel.GetDistinctServiceNames)
	e.GET("/otel/service/:serviceName/root-spans", otel.GetRootSpans)
	e.GET("/otel/service/:serviceName/root-spans-filtered", otel.GetRootSpansFiltered)
	e.GET("/otel/trace/:traceId/nested-spans", otel.GetNestedSpans)
	e.GET("/otel/trace/:traceId/span/:spanId", otel.GetSpan)
	e.GET("/otel/spans/type/workflow/:serviceName", otel.GetSpansTypeWorkflow)

	llm.RegisterRoutes(e)
}
