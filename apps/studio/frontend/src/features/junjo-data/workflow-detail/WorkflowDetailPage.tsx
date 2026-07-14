import { Link, useParams } from 'react-router'
import ErrorPage from '../../../components/errors/ErrorPage'
import { useEffect, useRef, useState } from 'react'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { selectSpanAndChildren, selectSpanById } from '../../traces/store/selectors'
import { RootState } from '../../../root-store/store'
import { getSpanDurationString } from '../../../util/duration-utils'
import WorkflowDetailNavButtons from './WorkflowDetailNavButtons'
import WorkflowDetailStateDiff from './WorkflowDetailStateDiff'
import { Switch } from '../../../components/forms/switch'
import RenderJunjoGraphList from '../../../mermaidjs/RenderJunjoGraphList'
import TabbedSpanLists from '../span-lists/TabbedSpanLists'
import WorkflowDetailStateNav from './WorkflowDetailStateNav'
import { TracesStateActions } from '../../traces/store/slice'
import { WorkflowDetailStateActions } from './store/slice'
import { useActiveWorkflowStoreDiagnostic } from './use-active-workflow-store-diagnostic'

export default function WorkflowDetailPage() {
  const { serviceName, traceId, workflowSpanId, spanId } = useParams()
  const dispatch = useAppDispatch()
  const [mermaidEdgeLabels, setMermaidEdgeLabels] = useState<boolean>(false)

  const loading = useAppSelector((state: RootState) => state.tracesState.loading)
  const error = useAppSelector((state: RootState) => state.tracesState.error)
  const workflowSpan = useAppSelector((state: RootState) =>
    selectSpanById(state, {
      traceId: traceId,
      spanId: workflowSpanId,
    }),
  )
  const workflowSpans = useAppSelector((state: RootState) =>
    selectSpanAndChildren(state, {
      traceId,
      spanId: workflowSpanId,
    }),
  )
  const routeTargetSpanId = spanId ?? workflowSpanId
  const routeTargetSpan = workflowSpans.find((span) => span.span_id === routeTargetSpanId)
  const activeSpan = useAppSelector((state: RootState) => state.workflowDetailState.activeSpan)
  const activeStoreDiagnostic = useActiveWorkflowStoreDiagnostic(
    traceId ?? '',
    workflowSpanId ?? '',
  )
  const workflowIdentity = traceId !== undefined && workflowSpanId !== undefined
    ? JSON.stringify([traceId, workflowSpanId])
    : null
  const routeTargetIdentity = workflowIdentity !== null && routeTargetSpanId !== undefined
    ? JSON.stringify([traceId, workflowSpanId, routeTargetSpanId])
    : null
  const initializedWorkflowIdentityRef = useRef<string | null>(null)
  const initializedRouteTargetIdentityRef = useRef<string | null>(null)
  const pendingRouteTargetIdentityRef = useRef<string | null>(null)
  const routeSelectionAlreadyMatches = initializedWorkflowIdentityRef.current === workflowIdentity
    && routeTargetSpan !== undefined
    && activeSpan?.trace_id === traceId
    && activeSpan?.span_id === routeTargetSpan.span_id

  // Data fetching
  useEffect(() => {
    // If the span does not yet exist in state, fetch it
    if (!workflowSpan) {
      dispatch(TracesStateActions.fetchTraceEvidence({ traceId }))
    }
  }, [dispatch, traceId, workflowSpan])

  // Workflow and URL target identities own the detail selection lifecycle. An
  // internal row click dispatches its span before changing the URL, so a target
  // that already matches preserves that row's event/failure selection. Direct
  // URL changes and different Workflows atomically replace all prior selection.
  useEffect(() => {
    if (workflowIdentity === null || routeTargetIdentity === null) {
      if (
        initializedWorkflowIdentityRef.current !== null
        || initializedRouteTargetIdentityRef.current !== null
        || pendingRouteTargetIdentityRef.current !== null
      ) {
        initializedWorkflowIdentityRef.current = null
        initializedRouteTargetIdentityRef.current = null
        pendingRouteTargetIdentityRef.current = null
        dispatch(WorkflowDetailStateActions.initializeWorkflowRoute(null))
      }
      return
    }
    if (initializedRouteTargetIdentityRef.current === routeTargetIdentity) return

    const baseIdentityMatches = initializedWorkflowIdentityRef.current === workflowIdentity
    const selectedTargetMatches = baseIdentityMatches
      && routeTargetSpan !== undefined
      && activeSpan?.trace_id === traceId
      && activeSpan?.span_id === routeTargetSpan.span_id

    if (routeTargetSpan !== undefined) {
      initializedWorkflowIdentityRef.current = workflowIdentity
      initializedRouteTargetIdentityRef.current = routeTargetIdentity
      pendingRouteTargetIdentityRef.current = null
      if (!selectedTargetMatches) {
        dispatch(WorkflowDetailStateActions.initializeWorkflowRoute(routeTargetSpan))
      }
      return
    }

    if (workflowSpan !== undefined) {
      initializedWorkflowIdentityRef.current = workflowIdentity
      initializedRouteTargetIdentityRef.current = routeTargetIdentity
      pendingRouteTargetIdentityRef.current = null
      dispatch(WorkflowDetailStateActions.initializeWorkflowRoute(null))
      return
    }

    if (pendingRouteTargetIdentityRef.current !== routeTargetIdentity) {
      initializedWorkflowIdentityRef.current = workflowIdentity
      initializedRouteTargetIdentityRef.current = null
      pendingRouteTargetIdentityRef.current = routeTargetIdentity
      dispatch(WorkflowDetailStateActions.initializeWorkflowRoute(null))
    }
  }, [activeSpan, dispatch, routeTargetIdentity, routeTargetSpan, traceId, workflowIdentity, workflowSpan])

  if (loading) return null

  if (error) {
    return <ErrorPage title={'Error'} message={`Error loading workflow span`} />
  }

  // No data rendering
  if (!serviceName || !traceId || !workflowSpanId || !workflowSpan) {
    return <div className={'p-2'}>No logs found.</div>
  }

  if (spanId !== undefined && routeTargetSpan === undefined) {
    return (
      <ErrorPage
        title={'Span not found'}
        message={`Span ${spanId} is not part of Workflow ${workflowSpanId}.`}
      />
    )
  }

  const routeSelectionReady = initializedRouteTargetIdentityRef.current === routeTargetIdentity
    || routeSelectionAlreadyMatches
  if (!routeSelectionReady) return null

  // Human readable start ingest time
  const date = new Date(workflowSpan.start_time)
  const readableStart = date.toLocaleString()

  // Parse duration
  const durationString = getSpanDurationString(workflowSpan.start_time, workflowSpan.end_time)

  return (
    <div className={'px-2 py-3 flex flex-col h-dvh overflow-hidden'}>
      <div className={'flex gap-x-3 px-2 items-center justify-between'}>
        <div>
          <div className={'mb-1 flex gap-x-3 font-bold'}>
            <Link to={'/logs'} className={'hover:underline'}>
              Logs
            </Link>
            <div>&rarr;</div>
            <div>{serviceName}</div>
            <div>&rarr;</div>
            <Link to={`/logs/${serviceName}`} className={'hover:underline'}>
              Workflow Executions
            </Link>
            <div>&rarr;</div>
            <div>
              {workflowSpan.name} <span className={'text-xs font-normal'}>({workflowSpanId})</span>
            </div>
          </div>
          <div className={'text-zinc-400 text-xs'}>
            {readableStart} &mdash; {durationString}
          </div>
        </div>
        <WorkflowDetailNavButtons serviceName={serviceName} workflowSpanId={workflowSpanId} />
      </div>

      <hr className={'my-4'} />

      <div className={`w-full shrink-0 pb-3 h-80 overflow-scroll shadow-md p-3 bg-zinc-50 dark:bg-zinc-800`}>
        <div className={'mb-2'}>
          <div className="w-44">
            <Switch label="Edge labels" checked={mermaidEdgeLabels} onCheckedChange={setMermaidEdgeLabels} />
          </div>
        </div>
        <RenderJunjoGraphList
          workflowSpanId={workflowSpanId}
          showEdgeLabels={mermaidEdgeLabels}
          traceId={traceId}
        />
      </div>
      <div className={'pt-2 px-2 pb-2'}>
        <WorkflowDetailStateNav
          traceId={traceId}
          diagnosticRequest={activeStoreDiagnostic.request}
        />
      </div>

      <div className={'grow w-full flex gap-x-4 justify-between overflow-hidden'}>
        <TabbedSpanLists
          traceId={traceId}
          workflowSpanId={workflowSpanId}
          storeDiagnosticRequest={activeStoreDiagnostic.request}
        />
        <WorkflowDetailStateDiff
          defaultWorkflowSpan={workflowSpan}
          activeStoreWorkflowSpan={activeStoreDiagnostic.ownerSpan}
          storeDiagnosticRequest={activeStoreDiagnostic.request}
        />
      </div>
    </div>
  )
}
