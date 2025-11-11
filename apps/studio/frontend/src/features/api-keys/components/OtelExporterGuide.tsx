import { useState, useEffect, ReactElement } from 'react'
import { ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline'
import { common, createStarryNight } from '@wooorm/starry-night'
import { toJsxRuntime } from 'hast-util-to-jsx-runtime'
import { Fragment, jsx, jsxs } from 'react/jsx-runtime'
import { useAppSelector } from '../../../root-store/hooks'
import { selectServiceNames } from '../../traces/store/selectors'
import '@wooorm/starry-night/style/both'

const codeExample = `from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

def init_otel(service_name: str):
    """Configure OpenTelemetry with JunjoOtelExporter."""

    # Create OpenTelemetry Resource
    resource = Resource.create({"service.name": service_name})

    # Set up tracing
    tracer_provider = TracerProvider(resource=resource)

    # JunjoOtelExporter - works alongside Honeycomb, Signoz, Jaeger, etc.
    junjo_exporter = JunjoOtelExporter(
        host="localhost",        # Dev: localhost | Prod: grpc.junjo.example.com
        port="50051",            # Dev: 50051 | Prod: 443 (or your port)
        api_key="YOUR_API_KEY",  # From API Keys page (set as environment variable)
        insecure=True,           # Set to False for production HTTPS
    )

    # Add Junjo span processor (can coexist with other processors)
    tracer_provider.add_span_processor(junjo_exporter.span_processor)

    # Set the tracer provider
    trace.set_tracer_provider(tracer_provider)`

export default function OtelExporterGuide() {
  const serviceNames = useAppSelector(selectServiceNames)
  const [isExpanded, setIsExpanded] = useState(serviceNames.length === 0)
  const [highlightedCode, setHighlightedCode] = useState<ReactElement | null>(null)

  useEffect(() => {
    async function highlightCode() {
      const starryNight = await createStarryNight(common)
      const scope = starryNight.flagToScope('py')

      if (scope) {
        const tree = starryNight.highlight(codeExample, scope)
        const content = toJsxRuntime(tree, { Fragment, jsx, jsxs })
        setHighlightedCode(content as ReactElement)
      }
    }

    highlightCode()
  }, [])

  return (
    <div className="max-w-4xl border border-zinc-200 dark:border-zinc-700 rounded-lg overflow-hidden">
      {/* Header - Always visible */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="font-semibold text-sm text-zinc-900 dark:text-zinc-100">
            Instructions: Configure OpenTelemetry Exporter
          </div>
        </div>
        {isExpanded ? (
          <ChevronUpIcon className="size-5 text-zinc-500 dark:text-zinc-400" />
        ) : (
          <ChevronDownIcon className="size-5 text-zinc-500 dark:text-zinc-400" />
        )}
      </button>

      {/* Expandable content */}
      {isExpanded && (
        <div className="px-4 py-4 bg-white dark:bg-zinc-900">
          <div className="space-y-4">
            {/* Introduction */}
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Add the Junjo exporter to your Python application. The exporter works alongside other
              observability providers like Honeycomb, Signoz, or Jaeger — simply add it as an additional span
              processor.
            </p>

            {/* Links */}
            <div className="flex flex-col gap-2 text-sm">
              <a
                href="https://python-api.junjo.ai/opentelemetry"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 dark:text-blue-400 hover:underline"
              >
                → Full OpenTelemetry Documentation
              </a>
              <a
                href="https://github.com/mdrideout/junjo/blob/main/examples/base/src/base/otel_config.py"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 dark:text-blue-400 hover:underline"
              >
                → Complete Implementation Example
              </a>
            </div>

            {/* Code example */}
            <div className="rounded-lg overflow-hidden border border-zinc-200 dark:border-zinc-700">
              <pre className="p-4 overflow-x-auto bg-zinc-50 dark:bg-[#0d1117] text-sm">
                <code>{highlightedCode || codeExample}</code>
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
