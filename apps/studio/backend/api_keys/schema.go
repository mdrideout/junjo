package api_keys

// Define request structure for creating an API key
type CreateAPIKeyRequest struct {
	Name string `json:"name" validate:"required"`
}
