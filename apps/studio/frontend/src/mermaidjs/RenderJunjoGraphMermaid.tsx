import mermaid from 'mermaid'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { JunjoSpanType, type OtelSpan } from '../features/traces/schemas/schemas'
import { selectTraceSpansForTraceId } from '../features/traces/store/selectors'
import { wrapSpan } from '../features/traces/utils/span-accessor'
import { selectWorkflowDetailActiveSpan } from '../features/junjo-data/workflow-detail/store/selectors'
import {
  spanSelection,
  WorkflowDetailStateActions,
} from '../features/junjo-data/workflow-detail/store/slice'
import { useWorkflowDetailRoute } from '../features/junjo-data/workflow-detail/workflow-detail-route-context'
import type { JGraph } from '../junjo-graph/schemas'
import { useAppDispatch, useAppSelector } from '../root-store/hooks'
import type { RootState } from '../root-store/store'
import {
  findIndexedGraphElementFromTarget,
  indexRenderedGraphElements,
  JUNJO_GRAPH_NODE_ATTRIBUTE,
} from './mermaid-dom-adapter'
import {
  findNearestSpanRepresentedInGraph,
  findRenderedGraphNodeIdForSpan,
  findSpanForRenderedGraphNodeId,
} from './junjo-graph-span-matching'

interface RenderJunjoGraphMermaidProps {
  graphSnapshot: JGraph
  traceId: string
  workflowChain: OtelSpan[]
  mermaidFlowString: string
  mermaidUniqueId: string
  workflowSpanId: string
}

let mermaidRenderSequence = 0

export default function RenderJunjoGraphMermaid({
  graphSnapshot,
  traceId,
  workflowChain,
  mermaidFlowString,
  mermaidUniqueId,
}: RenderJunjoGraphMermaidProps) {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const route = useWorkflowDetailRoute()
  const svgContainerRef = useRef<HTMLDivElement>(null)
  const graphElementIndexRef = useRef(new Map<string, Element>())
  const [renderVersion, setRenderVersion] = useState(0)

  const activeSpan = useAppSelector(
    (state: RootState) => selectWorkflowDetailActiveSpan(state),
  )
  const traceSpans = useAppSelector((state: RootState) =>
    selectTraceSpansForTraceId(state, { traceId }),
  )
  const graphSpans = useMemo(
    () => traceSpans.filter((span) => {
      const spanType = wrapSpan(span).junjoSpanType
      return (
        spanType === JunjoSpanType.NODE
        || spanType === JunjoSpanType.SUBFLOW
        || spanType === JunjoSpanType.RUN_CONCURRENT
      )
    }),
    [traceSpans],
  )
  const selectedGraphSpan = useMemo(
    () => findNearestSpanRepresentedInGraph(graphSnapshot, activeSpan, traceSpans),
    [activeSpan, graphSnapshot, traceSpans],
  )

  const findSpanForGraphNodeId = useCallback(
    (graphNodeId: string) =>
      findSpanForRenderedGraphNodeId(graphSnapshot, graphNodeId, graphSpans),
    [graphSnapshot, graphSpans],
  )

  useEffect(() => {
    const container = svgContainerRef.current
    if (container === null || mermaidFlowString.length === 0) return

    let cancelled = false
    mermaidRenderSequence += 1
    const svgId = `mermaid-svg-${mermaidUniqueId}-${mermaidRenderSequence}`

    void mermaid.render(svgId, mermaidFlowString)
      .then(({ svg, bindFunctions }) => {
        if (cancelled || svgContainerRef.current !== container) return
        container.innerHTML = svg
        bindFunctions?.(container)
        setRenderVersion((current) => current + 1)
      })
      .catch((reason: unknown) => {
        if (cancelled || svgContainerRef.current !== container) return
        const message = reason instanceof Error ? reason.message : String(reason)
        container.textContent = `Error rendering diagram: ${message}`
      })

    return () => {
      cancelled = true
    }
  }, [mermaidFlowString, mermaidUniqueId])

  useEffect(() => {
    const container = svgContainerRef.current
    if (container === null || renderVersion === 0) return

    const index = indexRenderedGraphElements(container, graphSnapshot)
    graphElementIndexRef.current = index

    for (const [graphNodeId, element] of index) {
      element.classList.remove(
        'graph-element-not-utilized',
        'node-subflow',
        'node-has-exception',
      )
      const span = findSpanForGraphNodeId(graphNodeId)
      if (span === undefined) {
        element.classList.add('graph-element-not-utilized')
        continue
      }
      if (wrapSpan(span).isSubflow) element.classList.add('node-subflow')
      if (wrapSpan(span).hasFailureSignal) element.classList.add('node-has-exception')
    }
  }, [findSpanForGraphNodeId, graphSnapshot, renderVersion])

  useEffect(() => {
    const container = svgContainerRef.current
    if (container === null) return

    const handleClick = (event: MouseEvent) => {
      const element = findIndexedGraphElementFromTarget(container, event.target)
      const graphNodeId = element?.getAttribute(JUNJO_GRAPH_NODE_ATTRIBUTE)
      if (graphNodeId === null || graphNodeId === undefined) return

      const clickedSpan = findSpanForGraphNodeId(graphNodeId)
      if (clickedSpan === undefined) return

      dispatch(WorkflowDetailStateActions.selectSpan(spanSelection(clickedSpan)))
      dispatch(WorkflowDetailStateActions.setActiveStateEvent(null))
      navigate(
        `/workflows/${route.serviceName}/${route.traceId}/${route.workflowSpanId}/${clickedSpan.span_id}`,
        { replace: true },
      )
    }

    container.addEventListener('click', handleClick)
    return () => container.removeEventListener('click', handleClick)
  }, [dispatch, findSpanForGraphNodeId, navigate, route])

  useEffect(() => {
    for (const element of graphElementIndexRef.current.values()) {
      element.classList.remove('mermaid-node-active')
    }
    if (selectedGraphSpan === undefined) return

    const graphNodeId = findRenderedGraphNodeIdForSpan(graphSnapshot, selectedGraphSpan)
    if (graphNodeId === null) return
    const activeElement = graphElementIndexRef.current.get(graphNodeId)
    if (activeElement === undefined) return

    activeElement.classList.add('mermaid-node-active')
    ;(activeElement as HTMLElement).scrollIntoView({
      behavior: 'smooth',
      block: 'center',
      inline: 'center',
    })
  }, [graphSnapshot, renderVersion, selectedGraphSpan])

  useEffect(() => {
    for (const element of graphElementIndexRef.current.values()) {
      element.classList.remove('node-subflow-active')
    }

    for (const workflowSpan of workflowChain) {
      const graphNodeId = findRenderedGraphNodeIdForSpan(graphSnapshot, workflowSpan)
      if (graphNodeId === null) continue
      graphElementIndexRef.current.get(graphNodeId)?.classList.add('node-subflow-active')
    }
  }, [graphSnapshot, renderVersion, workflowChain])

  return (
    <div
      ref={svgContainerRef}
      className="mermaid-container"
      id={`mermaid-container-${mermaidUniqueId}`}
    />
  )
}
