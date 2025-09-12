import { useParams } from 'react-router'
import { useEffect, useState } from 'react'
import { OtelSpan } from '../otel/schemas/schemas'
import { API_HOST } from '../../config'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { geminiTextRequest } from './fetch/gemini-text-request'
import { PromptPlaygroundActions } from './store/slice'
import { GeminiTextRequest } from './schemas/gemini-text-request'
import ModelSelector from './components/ModelSelector'

export default function PromptPlaygroundPage() {
  const { traceId, spanId } = useParams<{ traceId: string; spanId: string }>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [span, setSpan] = useState<OtelSpan | null>(null)
  const [originalModel, setOriginalModel] = useState<string | null>(null)
  const dispatch = useAppDispatch()
  const {
    output,
    loading: outputLoading,
    error: outputError,
  } = useAppSelector((state) => state.promptPlaygroundState)
  const selectedModel = useAppSelector((state) => state.promptPlaygroundState.selectedModel)

  useEffect(() => {
    if (span) {
      const modelName = span.attributes_json['llm.model_name'] || 'Unknown'
      dispatch(PromptPlaygroundActions.setSelectedModel(modelName))
      setOriginalModel(modelName)
    }
  }, [span, dispatch])

  useEffect(() => {
    const fetchSpan = async () => {
      try {
        setLoading(true)
        setError(false)
        const response = await fetch(`${API_HOST}/otel/trace/${traceId}/span/${spanId}`, {
          credentials: 'include',
        })
        if (!response.ok) {
          throw new Error('Failed to fetch span')
        }
        const data = await response.json()
        setSpan(data)
      } catch (error) {
        setError(true)
      } finally {
        setLoading(false)
      }
    }

    fetchSpan()
  }, [traceId, spanId, dispatch])

  if (loading) {
    return <div>Loading...</div>
  }

  if (error) {
    return <div>Error loading span.</div>
  }

  if (!span) {
    return <div>Span not found.</div>
  }

  const getInputValue = (value: any) => {
    if (typeof value === 'string') {
      try {
        const parsed = JSON.parse(value)
        if (parsed.contents) {
          return parsed.contents
        }
        return value
      } catch (e) {
        return value
      }
    }
    return ''
  }

  const getOutputValue = (attributes: any) => {
    // Try to get the output value from various possible attribute paths
    let outputValue =
      attributes['llm.output_messages.0.message.content'] ||
      attributes['output.value'] ||
      attributes['llm.output']

    if (outputValue) {
      // If it's a string, try to parse it as JSON
      if (typeof outputValue === 'string') {
        try {
          const parsed = JSON.parse(outputValue)

          // Check if it's a Gemini response with candidates structure
          if (parsed.candidates && Array.isArray(parsed.candidates)) {
            // Extract just the text content if available
            if (parsed.candidates[0]?.content?.parts?.[0]?.text) {
              return parsed.candidates[0].content.parts[0].text
            }
          }

          // For other JSON structures, format with indentation for readability
          return JSON.stringify(parsed, null, 2)
        } catch (e) {
          // If it's not valid JSON, return as-is
          return outputValue
        }
      }

      // If it's already an object, format it as JSON string with indentation
      if (typeof outputValue === 'object') {
        return JSON.stringify(outputValue, null, 2)
      }
    }

    return ''
  }

  const inputValue = getInputValue(span.attributes_json['input.value'])
  const outputValue = getOutputValue(span.attributes_json)
  const modelName = span.attributes_json['llm.model_name'] || 'Unknown'
  const provider = span.attributes_json['llm.provider'] || 'Unknown'

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const formData = new FormData(event.currentTarget)
    const prompt = formData.get('prompt') as string
    const model = selectedModel
    if (!model) {
      // Handle case where model is not selected
      console.error('No model selected')
      return
    }
    const payload: GeminiTextRequest = {
      model,
      contents: [{ parts: [{ text: prompt }] }],
    }
    dispatch(PromptPlaygroundActions.setOutput(null))
    const result = await geminiTextRequest(payload)
    if (result.candidates && result.candidates.length > 0) {
      const text = result.candidates[0].content.parts[0].text
      dispatch(PromptPlaygroundActions.setOutput(text))
    }
  }

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">Prompt Playground</h1>
        <div className="text-sm text-zinc-500">
          <div className="flex items-center gap-2">
            <span>{provider} / </span>
            <ModelSelector originalModel={originalModel} />
          </div>
        </div>
      </div>
      <form onSubmit={handleSubmit}>
        <div className="mb-4">
          <label htmlFor="prompt" className="block text-sm font-medium text-zinc-700">
            Prompt
          </label>
          <div className="mt-1">
            <textarea
              id="prompt"
              name="prompt"
              rows={10}
              className="p-2 shadow-sm focus:ring-indigo-500 focus:border-indigo-500 block w-full sm:text-sm border border-zinc-300 rounded-md resize-y"
              defaultValue={inputValue}
            />
          </div>
        </div>
        <div className="mb-4">
          <label htmlFor="output" className="block text-sm font-medium text-zinc-700">
            Output
          </label>
          <div className="mt-1">
            <textarea
              id="output"
              name="output"
              rows={10}
              className="p-2 shadow-sm focus:ring-indigo-500 focus:border-indigo-500 block w-full sm:text-sm border border-zinc-300 rounded-md resize-y"
              value={output || outputValue}
              readOnly
            />
          </div>
        </div>
        <button
          type="submit"
          className="px-3 py-1.5 text-sm font-semibold rounded-md bg-zinc-900 text-white hover:bg-zinc-800"
          disabled={outputLoading}
        >
          {outputLoading ? 'Loading...' : 'Submit'}
        </button>
        {outputError && <div className="text-red-500 mt-2">Error generating content</div>}
      </form>
    </div>
  )
}
