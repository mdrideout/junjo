package api

import (
	"database/sql"
	"junjo-ui-backend/db"
	"junjo-ui-backend/db_gen"
	"net/http"

	"github.com/labstack/echo/v4"
)

func GetWorkflowLogs(c echo.Context) error {
	c.Logger().Printf("Running GetWorkflowLogs function")

	// Get execId from query parameters
	execID := c.Param("execID")
	if execID == "" {
		return c.JSON(http.StatusBadRequest, map[string]string{
			"error": "execId is required",
		})
	}

	// Get database queries instance
	queries := db_gen.New(db.DB)

	// Call ListWorkflowLogs
	logs, err := queries.ListWorkflowLogs(c.Request().Context(), execID)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{
			"error": "Failed to fetch workflow logs",
		})
	}

	// Log the logs fetched
	c.Logger().Printf("Fetched %d logs for execId: %s", len(logs), execID)
	c.Logger().Printf("Logs: %+v", logs)

	// If no logs found, return empty array
	if len(logs) == 0 {
		return c.JSON(http.StatusOK, []string{})
	}

	return c.JSON(http.StatusOK, logs)
}

func GetWorkflowMetadata(c echo.Context) error {
	c.Logger().Printf("Running GetWorkflowMetadata function")

	// Get database queries instance
	queries := db_gen.New(db.DB)

	// Call ListWorkflowMetadata
	metadata, err := queries.ListWorkflowMetadata(c.Request().Context())
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{
			"error": "Failed to fetch workflow metadata",
		})
	}

	// Log the metadata fetched
	c.Logger().Printf("Fetched %d workflow metadata records", len(metadata))

	// If no metadata found, return empty array
	if len(metadata) == 0 {
		return c.JSON(http.StatusOK, []string{})
	}

	return c.JSON(http.StatusOK, metadata)
}

func GetWorkflowMetadataByExecID(c echo.Context) error {
	c.Logger().Printf("Running GetWorkflowMetadataByExecID function")

	// Get execId from query parameters
	execID := c.Param("execID")
	if execID == "" {
		return c.JSON(http.StatusBadRequest, map[string]string{
			"error": "execId is required",
		})
	}

	// Get database queries instance
	queries := db_gen.New(db.DB)

	// Call GetWorkflowMetadataByExecID
	metadata, err := queries.GetWorkflowMetadataByExecID(c.Request().Context(), execID)
	if err != nil {
		if err == sql.ErrNoRows {
			return c.JSON(http.StatusNotFound, map[string]string{
				"error": "No metadata found for execId: " + execID,
			})
		}

		c.Logger().Printf("Error: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{
			"error":   "Failed to fetch workflow metadata",
			"details": err.Error(),
		})
	}

	// Log the metadata fetched
	c.Logger().Printf("Fetched metadata for execId: %s", execID)

	return c.JSON(http.StatusOK, metadata)
}
