import { useState, useEffect, ReactElement } from 'react'
import { ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline'
import { common, createStarryNight } from '@wooorm/starry-night'
import { toJsxRuntime } from 'hast-util-to-jsx-runtime'
import { Fragment, jsx, jsxs } from 'react/jsx-runtime'
import { useAppSelector } from '../../../root-store/hooks'
import { selectServiceNames } from '../../traces/store/selectors'
import '@wooorm/starry-night/style/both'

const codeExample = `from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def init_otel(service_name: str):
    """Configure standard OTLP trace export to Junjo AI Studio."""

    # Create OpenTelemetry Resource
    resource = Resource.create({"service.name": service_name})

    # Set up tracing
    tracer_provider = TracerProvider(resource=resource)

    # Local Development Example
    studio_exporter = OTLPSpanExporter(
        endpoint="localhost:26155",
        headers=(("x-junjo-api-key", "YOUR_API_KEY"),),
        insecure=True,
        timeout=120,
    )

    # Production Example
    # studio_exporter = OTLPSpanExporter(
    #     endpoint="ingestion.example.com:443",
    #     headers=(("x-junjo-api-key", "YOUR_API_KEY"),),
    #     insecure=False,
    #     timeout=120,
    # )

    # This trace processor can coexist with processors for other destinations.
    tracer_provider.add_span_processor(BatchSpanProcessor(studio_exporter))

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
              Add a standard OTLP trace exporter to your Python application. Its span processor can coexist
              with other observability destinations such as Honeycomb, SigNoz, or Jaeger.
            </p>

            {/* Links */}
            <div className="flex flex-col gap-2 text-sm">
              <a
                href="https://junjo.ai/docs/studio/overview/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 dark:text-blue-400 hover:underline"
              >
                → Junjo AI Studio Telemetry Documentation
              </a>
              <a
                href="https://github.com/mdrideout/junjo/blob/master/apps/studio/deployments/vm-caddy/junjo_app/otel_config.py"
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
