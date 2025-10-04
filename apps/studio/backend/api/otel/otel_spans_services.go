package api_otel

import (
	_ "embed"
	"fmt"
	db_duckdb "junjo-server/db_duckdb"
	"net/http"

	"github.com/labstack/echo/v4"
)

//go:embed query_distinct_service_names.sql
var queryDistinctServiceNames string

//go:embed query_root_spans.sql
var queryRootSpans string

//go:embed query_nested_spans.sql
var queryNestedSpans string

//go:embed query_root_spans_filtered.sql
var queryRootSpansFiltered string

//go:embed query_span.sql
var querySpan string

//go:embed query_spans_type_workflow.sql
var querySpansTypeWorkflow string

func GetDistinctServiceNames(c echo.Context) error {
	c.Logger().Printf("Running GetDistinctServiceNames function")

	db := db_duckdb.DB
	if db == nil {
		return fmt.Errorf("database connection is nil")
	}

	// Execute the query
	rows, err := db.Query(queryDistinctServiceNames)
	if err != nil {
		c.Logger().Printf("Error querying database: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("database query failed: %v", err)})
	}
	defer rows.Close()

	// Create the array of strings from the row values
	serviceNames := []string{}
	for rows.Next() {
		var serviceName string
		if err := rows.Scan(&serviceName); err != nil {
			c.Logger().Printf("Error scanning row: %v", err)
		}
		serviceNames = append(serviceNames, serviceName)
	}

	return c.JSON(http.StatusOK, serviceNames)
}

func GetRootSpans(c echo.Context) error {
	serviceName := c.Param("serviceName")
	if serviceName == "" {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "serviceName parameter is required"})
	}
	c.Logger().Printf("Running GetRootSpans function for service %s", serviceName)

	db := db_duckdb.DB
	if db == nil {
		return fmt.Errorf("database connection is nil")
	}

	// Execute the query
	rows, err := db.Query(queryRootSpans, serviceName)
	if err != nil {
		c.Logger().Printf("Error querying database: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("database query failed: %v", err)})
	}
	defer rows.Close()

	// Get Column Names
	columns, err := rows.Columns()
	if err != nil {
		c.Logger().Printf("Error getting columns: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to get columns: %v", err)})
	}

	// Prepare data structures for dynamic scanning
	count := len(columns)
	values := make([]interface{}, count)
	valuePtrs := make([]interface{}, count)
	for i := range columns {
		valuePtrs[i] = &values[i]
	}

	// Final results storage
	results := []map[string]interface{}{}

	// Start processing each row
	for rows.Next() {
		if err := rows.Scan(valuePtrs...); err != nil {
			c.Logger().Printf("Error scanning row: %v", err)
			return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to scan row: %v", err)})
		}

		// Create a map for the current row
		rowMap := make(map[string]interface{})

		for i, colName := range columns {
			rowMap[colName] = values[i]
		}

		// Append this row to the results
		results = append(results, rowMap)
	}

	return c.JSON(http.StatusOK, results)
}

func GetRootSpansFiltered(c echo.Context) error {
	serviceName := c.Param("serviceName")
	if serviceName == "" {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "serviceName parameter is required"})
	}
	c.Logger().Printf("Running GetRootSpansFiltered function for service %s", serviceName)

	db := db_duckdb.DB
	if db == nil {
		return fmt.Errorf("database connection is nil")
	}

	// Execute the query
	rows, err := db.Query(queryRootSpansFiltered, serviceName)
	if err != nil {
		c.Logger().Printf("Error querying database: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("database query failed: %v", err)})
	}
	defer rows.Close()

	// Get Column Names
	columns, err := rows.Columns()
	if err != nil {
		c.Logger().Printf("Error getting columns: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to get columns: %v", err)})
	}

	// Prepare data structures for dynamic scanning
	count := len(columns)
	values := make([]interface{}, count)
	valuePtrs := make([]interface{}, count)
	for i := range columns {
		valuePtrs[i] = &values[i]
	}

	// Final results storage
	results := []map[string]interface{}{}

	// Start processing each row
	for rows.Next() {
		if err := rows.Scan(valuePtrs...); err != nil {
			c.Logger().Printf("Error scanning row: %v", err)
			return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to scan row: %v", err)})
		}

		// Create a map for the current row
		rowMap := make(map[string]interface{})

		for i, colName := range columns {
			rowMap[colName] = values[i]
		}

		// Append this row to the results
		results = append(results, rowMap)
	}

	return c.JSON(http.StatusOK, results)
}

func GetNestedSpans(c echo.Context) error {
	traceId := c.Param("traceId")
	if traceId == "" {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "traceId parameter is required"})
	}
	c.Logger().Printf("Running GetNestedSpans function for trace %s", traceId)

	db := db_duckdb.DB
	if db == nil {
		return fmt.Errorf("database connection is nil")
	}

	// Execute the query
	rows, err := db.Query(queryNestedSpans, traceId)
	if err != nil {
		c.Logger().Printf("Error querying database: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("database query failed: %v", err)})
	}
	defer rows.Close()

	// Get Column Names
	columns, err := rows.Columns()
	if err != nil {
		c.Logger().Printf("Error getting columns: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to get columns: %v", err)})
	}

	// Prepare data structures for dynamic scanning
	count := len(columns)
	values := make([]interface{}, count)
	valuePtrs := make([]interface{}, count)
	for i := range columns {
		valuePtrs[i] = &values[i]
	}

	// Final results storage
	results := []map[string]interface{}{}

	// Start processing each row
	for rows.Next() {
		if err := rows.Scan(valuePtrs...); err != nil {
			c.Logger().Printf("Error scanning row: %v", err)
			return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to scan row: %v", err)})
		}

		// Create a map for the current row
		rowMap := make(map[string]interface{})

		for i, colName := range columns {
			rowMap[colName] = values[i]
		}

		// Append this row to the results
		results = append(results, rowMap)
	}

	return c.JSON(http.StatusOK, results)
}

func GetSpan(c echo.Context) error {
	traceId := c.Param("traceId")
	if traceId == "" {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "traceId parameter is required"})
	}
	spanId := c.Param("spanId")
	if spanId == "" {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "spanId parameter is required"})
	}
	c.Logger().Printf("Running GetSpan function for trace %s and span %s", traceId, spanId)

	db := db_duckdb.DB
	if db == nil {
		return fmt.Errorf("database connection is nil")
	}

	// Execute the query
	rows, err := db.Query(querySpan, traceId, spanId)
	if err != nil {
		c.Logger().Printf("Error querying database: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("database query failed: %v", err)})
	}
	defer rows.Close()

	// Get Column Names
	columns, err := rows.Columns()
	if err != nil {
		c.Logger().Printf("Error getting columns: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to get columns: %v", err)})
	}

	// Prepare data structures for dynamic scanning
	count := len(columns)
	values := make([]interface{}, count)
	valuePtrs := make([]interface{}, count)
	for i := range columns {
		valuePtrs[i] = &values[i]
	}

	// Final results storage
	var result map[string]interface{}

	// Start processing each row
	if rows.Next() {
		if err := rows.Scan(valuePtrs...); err != nil {
			c.Logger().Printf("Error scanning row: %v", err)
			return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to scan row: %v", err)})
		}

		// Create a map for the current row
		rowMap := make(map[string]interface{})

		for i, colName := range columns {
			rowMap[colName] = values[i]
		}

		result = rowMap
	}

	return c.JSON(http.StatusOK, result)
}

func GetSpansTypeWorkflow(c echo.Context) error {
	c.Logger().Printf("Running GetSpansTypeWorkflow function")

	db := db_duckdb.DB
	if db == nil {
		return fmt.Errorf("database connection is nil")
	}

	// Execute the query
	rows, err := db.Query(querySpansTypeWorkflow)
	if err != nil {
		c.Logger().Printf("Error querying database: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("database query failed: %v", err)})
	}
	defer rows.Close()

	// Get Column Names
	columns, err := rows.Columns()
	if err != nil {
		c.Logger().Printf("Error getting columns: %v", err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to get columns: %v", err)})
	}

	// Prepare data structures for dynamic scanning
	count := len(columns)
	values := make([]interface{}, count)
	valuePtrs := make([]interface{}, count)
	for i := range columns {
		valuePtrs[i] = &values[i]
	}

	// Final results storage
	results := []map[string]interface{}{}

	// Start processing each row
	for rows.Next() {
		if err := rows.Scan(valuePtrs...); err != nil {
			c.Logger().Printf("Error scanning row: %v", err)
			return c.JSON(http.StatusInternalServerError, map[string]string{"error": fmt.Sprintf("failed to scan row: %v", err)})
		}

		// Create a map for the current row
		rowMap := make(map[string]interface{})

		for i, colName := range columns {
			rowMap[colName] = values[i]
		}

		// Append this row to the results
		results = append(results, rowMap)
	}

	return c.JSON(http.StatusOK, results)
}
