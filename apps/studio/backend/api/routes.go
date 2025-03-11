package api

import (
	"github.com/labstack/echo/v4"
)

func InitRoutes(e *echo.Echo) {
	e.GET("/workflow-logs/:execID", GetWorkflowLogs)
	e.GET("/workflow-metadata", GetWorkflowMetadata)
	e.GET("/workflow-metadata/:execID", GetWorkflowMetadataByExecID)
	e.GET("/app-names", GetUniqueAppNames)
	e.GET("/app-names/:AppName/workflow-executions", GetWorkflowMetadataByAppName)
}
