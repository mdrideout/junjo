package api_otel

import (
	_ "embed"
	"fmt"
	db_duckdb "junjo-server/db_duckdb"
	"net/http"

	"github.com/labstack/echo/v4"
)

//go:embed query_workflow_spans.sql
var queryWorkflowSpans string

//go:embed query_workflow_lineage.sql
var queryWorkflowLineage string

func GetWorkflowE2E(c echo.Context) error {
	c.Logger().Printf("Running GetOtelE2E function")

	// Get the workflow spans
	workflowSpans, err := GetWorkflowSpans(c)
	if err != nil {
		c.Logger().Printf("Error getting workflow spans: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to get workflow spans: %v", err)})
	}

	// Get the workflow lineage spans
	workflowLineage, err := GetWorkflowLineage(c)
	if err != nil {
		c.Logger().Printf("Error getting workflow lineage: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to get workflow lineage: %v", err)})
	}

	// Return both sets of spans
	return c.JSON(http.StatusOK, map[string]interface{}{
		"workflowSpans":   workflowSpans,
		"workflowLineage": workflowLineage,
	})
}

func GetWorkflowSpans(c echo.Context) ([]map[string]interface{}, error) {
	c.Logger().Printf("Running GetOtelSpans function")
	c.Logger().Printf("Query executing: %s", queryWorkflowSpans)

	db := db_duckdb.DB
	if db == nil {
		return nil, fmt.Errorf("database connection is nil")
	}

	// Execute the query
	rows, err := db.Query(queryWorkflowSpans)
	if err != nil {
		c.Logger().Printf("Error querying database: %v", err)
		return nil, c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("database query failed: %v", err)})
	}
	defer rows.Close()

	// Get Column Names
	columns, err := rows.Columns()
	if err != nil {
		c.Logger().Printf("Error getting columns: %v", err)
		return nil, c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to get columns: %v", err)})
	}

	c.Logger().Printf("Columns: %v", columns)

	// Prepare data structures for dynamic scanning
	count := len(columns)
	values := make([]interface{}, count)    // The storage of row data
	valuePtrs := make([]interface{}, count) // Pointers to the storage
	for i := range columns {
		valuePtrs[i] = &values[i] // Link the slices, valuePtrs[i] = memory address of the value storage location
	}

	// Final results storage
	var results []map[string]interface{}

	// Start processing each row
	for rows.Next() {
		// Provide the memory address (via pointers) of the
		// storage locations of the row's column data
		// and populate the database data into the values slice
		if err := rows.Scan(valuePtrs...); err != nil {
			c.Logger().Printf("Error scanning row: %v", err)
			return nil, c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to scan row: %v", err)})
		}

		// Create a map for the current row
		rowMap := make(map[string]interface{})

		for i, colName := range columns {
			val := values[i]      // Get the raw value of the current column
			_, ok := val.([]byte) // Check if its a []byte
			if ok {
				// TEMP write a string
				c.Logger().Printf("Column %s is a byte slice.", colName)
				rowMap[colName] = "BYTE SLICE"

				// Handle []byte columns:

			} else {
				rowMap[colName] = val // Store directly if not a []byte
			}
		}

		// Append this row to the results
		results = append(results, rowMap)
	}

	c.Logger().Printf("Results: %v", results)
	return results, nil
}

func GetWorkflowLineage(c echo.Context) ([]map[string]interface{}, error) {
	c.Logger().Printf("Running GetWorkflowLineage function")
	c.Logger().Printf("Query executing: %s", queryWorkflowLineage)

	db := db_duckdb.DB
	if db == nil {
		return nil, fmt.Errorf("database connection is nil")
	}

	// Execute the query
	rows, err := db.Query(queryWorkflowLineage)
	if err != nil {
		c.Logger().Printf("Error querying database: %v", err)
		return nil, c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("database query failed: %v", err)})
	}
	defer rows.Close()

	// Get Column Names
	columns, err := rows.Columns()
	if err != nil {
		c.Logger().Printf("Error getting columns: %v", err)
		return nil, c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to get columns: %v", err)})
	}

	c.Logger().Printf("Columns: %v", columns)

	// Prepare data structures for dynamic scanning
	count := len(columns)
	values := make([]interface{}, count)    // The storage of row data
	valuePtrs := make([]interface{}, count) // Pointers to the storage
	for i := range columns {
		valuePtrs[i] = &values[i] // Link the slices, valuePtrs[i] = memory address of the value storage location
	}

	// Final results storage
	var results []map[string]interface{}

	// Start processing each row
	for rows.Next() {
		// Provide the memory address (via pointers) of the
		// storage locations of the row's column data
		// and populate the database data into the values slice
		if err := rows.Scan(valuePtrs...); err != nil {
			c.Logger().Printf("Error scanning row: %v", err)
			return nil, c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to scan row: %v", err)})
		}

		// Create a map for the current row
		rowMap := make(map[string]interface{})

		for i, colName := range columns {
			val := values[i]      // Get the raw value of the current column
			_, ok := val.([]byte) // Check if its a []byte
			if ok {
				// TEMP write a string
				c.Logger().Printf("Column %s is a byte slice.", colName)
				rowMap[colName] = "BYTE SLICE"

				// Handle []byte columns:

			} else {
				rowMap[colName] = val // Store directly if not a []byte
			}
		}

		// Append this row to the results
		results = append(results, rowMap)
	}

	c.Logger().Printf("Results: %v", results)
	return results, nil
}
