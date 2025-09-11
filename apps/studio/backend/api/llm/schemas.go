package llm

// GeminiPart represents a part of a content message.
type GeminiPart struct {
	Text string `json:"text"`
}

// GeminiContent represents the content of a message.
type GeminiContent struct {
	Role  string       `json:"role,omitempty"`
	Parts []GeminiPart `json:"parts"`
}

// GenerationConfig specifies the generation parameters for the model.
type GenerationConfig struct {
	StopSequences []string `json:"stopSequences,omitempty"`
	Temperature   float64  `json:"temperature,omitempty"`
	TopP          float64  `json:"topP,omitempty"`
	TopK          int      `json:"topK,omitempty"`
}

// SystemInstruction provides system-level instructions to the model.
type SystemInstruction struct {
	Parts []GeminiPart `json:"parts"`
}

// GeminiRequest is the request body for the Gemini API.
type GeminiRequest struct {
	Model             string             `json:"model,omitempty"`
	Contents          []GeminiContent    `json:"contents"`
	GenerationConfig  *GenerationConfig  `json:"generationConfig,omitempty"`
	SystemInstruction *SystemInstruction `json:"system_instruction,omitempty"`
}
