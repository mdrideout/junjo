package llm

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
)

const geminiAPIBaseURL = "https://generativelanguage.googleapis.com/v1beta/models/"

// GeminiService is a service for interacting with the Gemini API.
type GeminiService struct{}

// NewGeminiService creates a new GeminiService.
func NewGeminiService() *GeminiService {
	return &GeminiService{}
}

// GenerateContent sends a request to the Gemini API to generate content.
func (s *GeminiService) GenerateContent(requestBody GeminiRequest) ([]byte, error) {
	apiKey := os.Getenv("GEMINI_API_KEY")
	if apiKey == "" {
		return nil, fmt.Errorf("GEMINI_API_KEY environment variable is not set")
	}

	// Construct the full API URL with the model from the request
	apiURL := fmt.Sprintf("%s%s:generateContent", geminiAPIBaseURL, requestBody.Model)

	jsonData, err := json.Marshal(requestBody)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", apiURL, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, err
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-goog-api-key", apiKey)

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	return io.ReadAll(resp.Body)
}
