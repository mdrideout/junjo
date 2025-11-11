# LiteLLM Provider Warning: Structured Output Schema Telemetry

## Context: Provider Warnings System

The provider warnings system detects suboptimal LLM configuration patterns that produce identical API behavior but capture different levels of detail in telemetry/observability data. These warnings help developers improve their instrumentation without changing application functionality.

### Why This Matters

When using structured outputs with LLM providers, the way you specify schemas affects what information gets captured in your telemetry spans. Poor schema telemetry makes it impossible to:
- Reconstruct the exact schema in observability tools
- Debug schema-related issues in production
- Understand what structure was requested in prompt playgrounds
- Analyze schema evolution over time

## LiteLLM Structured Output Issue

### The Problem

When using LiteLLM with Pydantic models for structured outputs, passing the model class directly may only capture the class name in telemetry, not the full JSON schema structure.

**Telemetry Capture Timing:** Telemetry systems capture the configuration parameters *before* LiteLLM's internal processing. If the schema conversion happens inside the library after telemetry capture, only the raw input (class name) is recorded.

### Detection Strategy

For LiteLLM provider warnings, check `llm.provider` for `litellm` and inspect `llm.invocation_parameters` or `input.value` for:
- `response_format` parameter containing a Pydantic class reference (string representation)
- Absence of explicit `model_json_schema()` call pattern

### Recommended Approach

#### ❌ Bad: Only Class Name in Telemetry

```python
from litellm import completion
from pydantic import BaseModel

class OutputSchema(BaseModel):
    result: str
    items: list[str]
    confidence: float

# This may work functionally, but telemetry only captures class name
response = completion(
    model="gemini/gemini-2.0-flash-exp",
    messages=[{"role": "user", "content": "Your prompt here"}],
    response_format=OutputSchema  # ⚠️ Only "OutputSchema" in telemetry
)

# Telemetry captures: "response_format": "OutputSchema"
# Missing: Full schema with properties, types, descriptions, etc.
```

#### ✅ Good: Full Schema Structure in Telemetry

```python
from litellm import completion
from pydantic import BaseModel

class OutputSchema(BaseModel):
    result: str
    items: list[str]
    confidence: float

# Explicitly convert to JSON schema for full telemetry capture
response = completion(
    model="gemini/gemini-2.0-flash-exp",
    messages=[{"role": "user", "content": "Your prompt here"}],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "OutputSchema",
            "schema": OutputSchema.model_json_schema(),  # ✅ Full schema dict
            "strict": True  # Optional: enforce strict schema adherence
        }
    }
)

# Telemetry captures: Full JSON schema with:
# - All properties (result, items, confidence)
# - Types (string, array, number)
# - Descriptions (if defined in model)
# - Required fields
# - Additional validation constraints
```

## Technical Reasoning

### Schema Exposure Before Library Processing

**Why call `model_json_schema()` explicitly:**

1. **Telemetry Timing:** OpenTelemetry instrumentation captures function parameters at call time, before LiteLLM processes them internally.

2. **Pydantic Conversion:** `model_json_schema()` converts the Pydantic class to a JSON Schema dict (OpenAI 3.1.0 / JSON Schema Draft 2020-12 format).

3. **Structured Format:** By passing the schema dict instead of the class, telemetry systems can serialize and store the complete structure.

4. **Provider Compatibility:** The `response_format` structure with `type: "json_schema"` follows OpenAI's API format, which LiteLLM adopts for cross-provider compatibility.

### Format Origin

This format is derived from:
- **OpenAI's Structured Outputs API:** Uses `response_format` with `type: "json_schema"` for structured outputs
- **Pydantic Integration:** `BaseModel.model_json_schema()` produces OpenAI 3.1.0 compatible schema dicts
- **User-verified pattern:** Combining these two produces full telemetry capture while maintaining identical API behavior

### Comparison with Other Libraries

**Google GenAI SDK (native):**
- Has `response_schema` (class) vs `response_json_schema` (dict) parameters
- Both work identically at API level
- Only `response_json_schema` captures full schema in telemetry
- SDK internally converts OpenAI 3.1.0 → OpenAI 3.0 for Gemini API

**LiteLLM:**
- Follows OpenAI's `response_format` structure
- Accepts Pydantic class directly OR explicit schema dict
- Telemetry capture depends on which format you use
- Does NOT automatically perform the same schema conversion as native SDKs

## Benefits of Explicit Schema

1. **Complete Observability:** Telemetry tools capture full schema structure
2. **Playground Reconstruction:** Prompt playgrounds can reconstruct the exact schema used
3. **Schema Versioning:** Track schema changes over time in your traces
4. **Debugging:** Understand what structure was requested when investigating issues
5. **Documentation:** Traces become self-documenting with embedded schemas
6. **Identical Behavior:** Same API request, better instrumentation

## Implementation Notes

### Future Provider Warning

When implementing the LiteLLM warning detector:

```typescript
function detectLiteLLMWarnings(span: OtelSpan): ProviderWarning | null {
  const provider = span.attributes_json['llm.provider']

  // Check if this is a LiteLLM call
  if (provider !== 'litellm') {
    return null
  }

  // Check for direct Pydantic class usage without explicit model_json_schema()
  // Look for response_format that doesn't contain "json_schema" object structure
  const invocationParams = span.attributes_json['llm.invocation_parameters']

  // Detection logic here...
  // Look for response_format without nested json_schema.schema structure

  if (hasDirectPydanticUsage) {
    return {
      title: 'Improve Telemetry: Use Explicit JSON Schema with LiteLLM',
      description: '...',
      codeExampleBad: '...',
      codeExampleGood: '...',
      learnMoreUrl: 'https://docs.litellm.ai/docs/completion/json_mode'
    }
  }

  return null
}
```

### References

- **LiteLLM JSON Mode Docs:** https://docs.litellm.ai/docs/completion/json_mode
- **OpenAI Structured Outputs:** https://cookbook.openai.com/examples/structured_outputs_intro
- **Pydantic JSON Schema:** https://docs.pydantic.dev/latest/concepts/json_schema/
- **User verification source:** Azure OpenAI Q&A showing `schema: Output.model_json_schema()` pattern

## Open Questions

1. **Detection Accuracy:** How to reliably detect when LiteLLM is being used vs. direct OpenAI SDK?
2. **Provider Identification:** What value does `llm.provider` show for LiteLLM calls? (May vary by underlying provider)
3. **False Positives:** Can we differentiate between LiteLLM with explicit schema vs. LiteLLM with class?
4. **Schema Validation:** Should we validate that the schema field contains a proper dict structure?

---

*Created: 2025-10-24*
*Context: Building provider-specific warnings for prompt playground to improve telemetry quality*
