import { Link, useParams } from 'react-router'
import { useEffect, useState } from 'react'
import { OtelSpan } from '../otel/schemas/schemas'
import { API_HOST } from '../../config'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { geminiTextRequest } from './fetch/gemini-text-request'
import { PromptPlaygroundActions } from './store/slice'
import { GeminiTextRequest } from './schemas/gemini-text-request'
import ModelSelector from './components/ModelSelector'
import { Switch } from '../../components/catalyst/switch'
import { getSpanDurationString } from '../../util/duration-utils'

export default function PromptPlaygroundPage() {
  const { serviceName, traceId, spanId } = useParams<{
    serviceName: string
    traceId: string
    spanId: string
  }>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [span, setSpan] = useState<OtelSpan | null>(null)
  const [originalModel, setOriginalModel] = useState<string | null>(null)
  const [testStartTime, setTestStartTime] = useState<string | null>(null)
  const [testEndTime, setTestEndTime] = useState<string | null>(null)
  const dispatch = useAppDispatch()
  const {
    output,
    loading: outputLoading,
    error: outputError,
  } = useAppSelector((state) => state.promptPlaygroundState)
  const selectedModel = useAppSelector((state) => state.promptPlaygroundState.selectedModel)
  const jsonMode = useAppSelector((state) => state.promptPlaygroundState.jsonMode)

  useEffect(() => {
    if (span) {
      const modelName = span.attributes_json['llm.model_name'] || 'Unknown'
      dispatch(PromptPlaygroundActions.setSelectedModel(modelName))
      setOriginalModel(modelName)
    }
    if (span) {
      const mimeType = span.attributes_json['input.mime_type']
      if (mimeType === 'application/json') {
        dispatch(PromptPlaygroundActions.setJsonMode(true))
      }
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
  const mimeType = span.attributes_json['input.mime_type'] || ''

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setTestStartTime(new Date().toISOString())
    setTestEndTime(null)
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

    if (jsonMode) {
      payload.generationConfig = {
        responseMimeType: 'application/json',
      }
    }
    dispatch(PromptPlaygroundActions.setOutput(null))
    const result = await geminiTextRequest(payload)
    if (result.candidates && result.candidates.length > 0) {
      const text = result.candidates[0].content.parts[0].text
      dispatch(PromptPlaygroundActions.setOutput(text))
    }
    setTestEndTime(new Date().toISOString())
  }

  return (
    <div className={'px-2 py-3 flex flex-col h-dvh overflow-hidden'}>
      <div className={'px-2 pb-4'}>
        <div className={'mb-1 flex gap-x-3 font-bold'}>
          <Link to={'/logs'} className={'hover:underline'}>
            Logs
          </Link>
          <div>&rarr;</div>
          <Link to={`/logs/${serviceName}`} className={'hover:underline'}>
            {serviceName}
          </Link>
          <div>&rarr;</div>
          <Link to={`/traces/${serviceName}`} className={'hover:underline'}>
            Traces
          </Link>
          <div>&rarr;</div>
          <Link to={`/traces/${serviceName}/${traceId}`} className={'hover:underline'}>
            {traceId}
          </Link>
          <div>&rarr;</div>
          <Link to={`/traces/${serviceName}/${traceId}/${spanId}`} className={'hover:underline'}>
            {spanId}
          </Link>
          <div>&rarr;</div>
          <div>Prompt Playground</div>
        </div>
        <div className={'text-zinc-400 text-xs'}>readableDate</div>
      </div>
      <hr />
      <div className={'overflow-scroll pt-4 pb-10'}>
        <div className="flex gap-8">
          {/* Left Column: Original */}
          <div className="w-1/2">
            <div className="flex justify-between items-center mb-4">
              <div className="text-2xl font-bold mb-2 dark:text-white">Original</div>
              <div className="text-sm text-zinc-500 dark:text-zinc-400 mb-2">
                {provider} / {modelName}
                {mimeType && (
                  <span className="ml-2 px-2 py-1 text-xs font-semibold rounded-full bg-zinc-200 text-zinc-800 dark:bg-zinc-700 dark:text-zinc-200">
                    {mimeType}
                  </span>
                )}
              </div>
            </div>

            <div className="mb-4">
              <label
                htmlFor="original-prompt"
                className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                Prompt
              </label>
              <div className="mt-1">
                <textarea
                  id="original-prompt"
                  rows={15}
                  className="p-2 shadow-sm focus:ring-indigo-500 focus:border-indigo-500 block w-full sm:text-sm border border-zinc-300 rounded-md resize-y bg-zinc-50 dark:bg-zinc-800 dark:border-zinc-700 dark:text-zinc-300"
                  value={inputValue}
                  readOnly
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between items-center">
                <label
                  htmlFor="original-output"
                  className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                >
                  Output
                </label>
                <div className="text-sm text-zinc-500 dark:text-zinc-400">
                  {getSpanDurationString(span.start_time, span.end_time)}
                </div>
              </div>
              <div className="mt-1">
                <textarea
                  id="original-output"
                  rows={15}
                  className="p-2 shadow-sm focus:ring-indigo-500 focus:border-indigo-500 block w-full sm:text-sm border border-zinc-300 rounded-md resize-y bg-zinc-50 dark:bg-zinc-800 dark:border-zinc-700 dark:text-zinc-300"
                  value={outputValue}
                  readOnly
                />
              </div>
            </div>
          </div>

          {/* Right Column: Playground */}
          <div className="w-1/2">
            <div className="flex justify-between items-center mb-4">
              <div className="text-2xl font-bold dark:text-white">Test</div>
              <div className="text-sm text-zinc-500 dark:text-zinc-400">
                <div className="flex items-center gap-2">
                  <ModelSelector originalModel={originalModel} />
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={jsonMode}
                      onChange={(checked) => dispatch(PromptPlaygroundActions.setJsonMode(checked))}
                      className="group"
                    />
                    <span className="text-sm text-zinc-500 dark:text-zinc-400">JSON Mode</span>
                  </div>
                </div>
              </div>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="mb-4">
                <label
                  htmlFor="prompt"
                  className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                >
                  Prompt
                </label>
                <div className="mt-1">
                  <textarea
                    id="prompt"
                    name="prompt"
                    rows={15}
                    className="p-2 shadow-sm focus:ring-indigo-500 focus:border-indigo-500 block w-full sm:text-sm border border-zinc-300 rounded-md resize-y dark:bg-zinc-900 dark:border-zinc-700 dark:text-zinc-300"
                    defaultValue={inputValue}
                  />
                </div>
              </div>
              <div className="mb-4">
                <div className="flex justify-between items-center">
                  <label
                    htmlFor="output"
                    className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                  >
                    Output
                  </label>
                  <div className="text-sm text-zinc-500 dark:text-zinc-400">
                    {testStartTime && testEndTime ? getSpanDurationString(testStartTime, testEndTime) : ''}
                  </div>
                </div>
                <div className="mt-1">
                  <textarea
                    id="output"
                    name="output"
                    rows={15}
                    className="p-2 shadow-sm focus:ring-indigo-500 focus:border-indigo-500 block w-full sm:text-sm border border-zinc-300 rounded-md resize-y dark:bg-zinc-900 dark:border-zinc-700 dark:text-zinc-300"
                    value={output || ''}
                    readOnly
                  />
                </div>
              </div>
              <button
                type="submit"
                className="px-3 py-1.5 text-sm font-semibold rounded-md bg-zinc-900 text-white hover:bg-zinc-800 dark:bg-indigo-600 dark:hover:bg-indigo-500"
                disabled={outputLoading}
              >
                {outputLoading ? 'Loading...' : 'Generate'}
              </button>
              {outputError && <div className="text-red-500 mt-2">Error generating content</div>}
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
