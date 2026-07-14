import { useEffect, useMemo, useRef, useState } from 'react'
import JsonView from '@uiw/react-json-view'
import { lightTheme } from '@uiw/react-json-view/light'
import { vscodeTheme } from '@uiw/react-json-view/vscode'
import { detailedDiff, diff } from 'deep-object-diff'
import { TriangleDownIcon } from '@radix-ui/react-icons'
import { ExclamationTriangleIcon } from '@heroicons/react/24/solid'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { OtelSpan } from '../../traces/schemas/schemas'
import SpanFailuresList from './SpanFailuresList'
import SpanAttributesContent from '../../traces/SpanAttributesContent'
import { wrapSpan } from '../../traces/utils/span-accessor'
import type { WorkflowStoreDiagnosticRequest } from '../../workflow-executions/hooks/use-workflow-store-diagnostic'
import { WorkflowStoreEvidenceBanner } from '../../workflow-executions/components/WorkflowStoreEvidenceBanner'
import {
  stateEventIdentityKey,
  transitionStateEventIdentity,
} from './state-event-identity'

enum DiffTabOptions {
  BEFORE = 'Before',
  AFTER = 'After',
  PATCH = 'Patch',
  CHANGES = 'Changes',
  DETAILED = 'Detailed',
  FAILURES = 'Failures',
  SPAN_DETAILS = 'Span Details',
}

interface WorkflowDetailStateDiffProps {
  defaultWorkflowSpan: OtelSpan
  activeStoreWorkflowSpan: OtelSpan | undefined
  storeDiagnosticRequest: WorkflowStoreDiagnosticRequest
}

const STATE_TABS = new Set([
  DiffTabOptions.BEFORE,
  DiffTabOptions.AFTER,
  DiffTabOptions.PATCH,
  DiffTabOptions.CHANGES,
  DiffTabOptions.DETAILED,
])

function jsonViewValue(value: unknown): object {
  return typeof value === 'object' && value !== null ? value : { value }
}

const TabButton = ({
  tab,
  activeTab,
  tabChangeHandler,
}: {
  tab: DiffTabOptions
  activeTab: DiffTabOptions
  tabChangeHandler: (tab: DiffTabOptions) => void
}) => (
  <button
    className={`leading-tight px-2 py-1 hover:bg-zinc-100 dark:hover:bg-zinc-700 text-sm font-medium border-b transition-all duration-200 cursor-pointer ${activeTab === tab ? 'border-zinc-600 ' : 'border-transparent'}`}
    onClick={() => tabChangeHandler(tab)}
  >
    <div className="flex items-center gap-x-1 text-left">
      {tab === DiffTabOptions.FAILURES && <ExclamationTriangleIcon className="size-4 text-red-700" />}
      {tab}
    </div>
  </button>
)

/**
 * Workflow State diagnostics use backend-verified Store projections. This UI
 * selects and compares those projections; it never interprets or replays raw
 * telemetry patches in the browser.
 */
export default function WorkflowDetailStateDiff({
  defaultWorkflowSpan,
  activeStoreWorkflowSpan,
  storeDiagnosticRequest,
}: WorkflowDetailStateDiffProps) {
  const hasMountedRef = useRef(false)
  const openFailuresTrigger = useAppSelector(
    (state: RootState) => state.workflowDetailState.openFailuresTrigger,
  )
  const activeSpan = useAppSelector((state: RootState) => state.workflowDetailState.activeSpan)
  const activeStateEvent = useAppSelector(
    (state: RootState) => state.workflowDetailState.activeStateEvent,
  )
  const hasFailures = activeSpan ? wrapSpan(activeSpan).hasFailureSignal : false
  const state = storeDiagnosticRequest.data?.state ?? null
  const replayVerified = state?.reconstruction_status === 'verified' && state.reconstructable

  const activeTransition = useMemo(() => {
    const storeId = state?.store_id
    return activeStateEvent === null || storeId === null || storeId === undefined
      ? null
      : state?.transitions.find(
        (transition) => stateEventIdentityKey(transitionStateEventIdentity(storeId, transition))
          === stateEventIdentityKey(activeStateEvent),
      ) ?? null
  }, [activeStateEvent, state])
  const activeSpanTransitions = useMemo(
    () => [...(state?.transitions ?? [])]
      .filter((transition) => transition.span_id === activeSpan?.span_id)
      .sort((left, right) => left.sequence - right.sequence),
    [activeSpan?.span_id, state],
  )
  const selectedTransitionMissing = activeStateEvent !== null && activeTransition === null
  const activeSpanIsStoreOwner = activeSpan?.span_id === activeStoreWorkflowSpan?.span_id
  const spanStateBoundaryAvailable = activeSpanIsStoreOwner || activeSpanTransitions.length > 0
  const stateViewsAvailable = replayVerified
    && !selectedTransitionMissing
    && (activeTransition !== null || spanStateBoundaryAvailable)

  const startValue = state?.start?.value
  const endValue = state?.end?.value
  const firstSpanTransition = activeSpanTransitions.at(0) ?? null
  const lastSpanTransition = activeSpanTransitions.at(-1) ?? null
  const beforeValue = activeTransition !== null
    ? activeTransition.before
    : activeSpanIsStoreOwner
      ? startValue
      : firstSpanTransition?.before
  const afterValue = activeTransition !== null
    ? activeTransition.after
    : activeSpanIsStoreOwner
      ? endValue
      : lastSpanTransition?.after
  const patchValue = activeTransition?.patch.value ?? {}
  const beforeJson = jsonViewValue(beforeValue)
  const afterJson = jsonViewValue(afterValue)
  const patchJson = jsonViewValue(patchValue)
  const changesJson = diff(beforeJson, afterJson)
  const detailedJson = detailedDiff(beforeJson, afterJson)

  const defaultTab = activeStateEvent ? DiffTabOptions.AFTER : DiffTabOptions.SPAN_DETAILS
  const [activeTab, setActiveTab] = useState<DiffTabOptions>(defaultTab)
  const [prefersDarkMode, setPrefersDarkMode] = useState(false)
  const displayTheme = prefersDarkMode ? vscodeTheme : lightTheme

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    setPrefersDarkMode(mediaQuery.matches)
    const listener = (event: MediaQueryListEvent) => setPrefersDarkMode(event.matches)
    mediaQuery.addEventListener('change', listener)
    return () => mediaQuery.removeEventListener('change', listener)
  }, [])

  useEffect(() => {
    if (!hasMountedRef.current) {
      hasMountedRef.current = true
      return
    }
    if (openFailuresTrigger != null) setActiveTab(DiffTabOptions.FAILURES)
  }, [openFailuresTrigger])

  useEffect(() => {
    if (activeTab === DiffTabOptions.FAILURES && !hasFailures) setActiveTab(defaultTab)
  }, [activeTab, defaultTab, hasFailures])

  useEffect(() => {
    if (activeStateEvent === null) {
      setActiveTab(DiffTabOptions.SPAN_DETAILS)
      return
    }
    setActiveTab((currentTab) =>
      currentTab === DiffTabOptions.SPAN_DETAILS ? DiffTabOptions.AFTER : currentTab,
    )
  }, [activeStateEvent])

  useEffect(() => {
    if (!stateViewsAvailable && STATE_TABS.has(activeTab)) {
      setActiveTab(DiffTabOptions.SPAN_DETAILS)
    }
  }, [activeTab, stateViewsAvailable])

  const getTabCollapsedLevel = (tab: DiffTabOptions) => {
    if (tab === DiffTabOptions.PATCH) return 3
    return 2
  }
  const getTabJsonData = (tab: DiffTabOptions) => {
    if (tab === DiffTabOptions.BEFORE) return beforeJson
    if (tab === DiffTabOptions.AFTER) return afterJson
    if (tab === DiffTabOptions.CHANGES) return changesJson
    if (tab === DiffTabOptions.DETAILED) return detailedJson
    if (tab === DiffTabOptions.PATCH) return patchJson
    return {}
  }

  return (
    <div className="flex-1/2 flex flex-col pr-2.5">
      <div className="flex gap-x-2 items-center">
        <div className="leading-tight pl-2 py-1 text-sm font-bold">State:</div>
        {stateViewsAvailable && (
          <>
            <TabButton tab={DiffTabOptions.BEFORE} activeTab={activeTab} tabChangeHandler={setActiveTab} />
            <TabButton tab={DiffTabOptions.AFTER} activeTab={activeTab} tabChangeHandler={setActiveTab} />
            {activeTransition !== null && (
              <TabButton tab={DiffTabOptions.PATCH} activeTab={activeTab} tabChangeHandler={setActiveTab} />
            )}
            <TabButton tab={DiffTabOptions.CHANGES} activeTab={activeTab} tabChangeHandler={setActiveTab} />
            <TabButton tab={DiffTabOptions.DETAILED} activeTab={activeTab} tabChangeHandler={setActiveTab} />
            <span aria-hidden="true">|</span>
          </>
        )}
        {activeSpan && (
          <TabButton
            tab={DiffTabOptions.SPAN_DETAILS}
            activeTab={activeTab}
            tabChangeHandler={setActiveTab}
          />
        )}
        {hasFailures && (
          <TabButton tab={DiffTabOptions.FAILURES} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        )}
      </div>
      <WorkflowStoreEvidenceBanner
        diagnostic={storeDiagnosticRequest.data}
        loading={storeDiagnosticRequest.loading}
        error={storeDiagnosticRequest.error}
        ownerIdentified={activeStoreWorkflowSpan !== undefined}
      />
      {selectedTransitionMissing && replayVerified && (
        <div className="border-t border-red-300 bg-red-50 px-3 py-2 text-xs text-red-950 dark:border-red-900 dark:bg-red-950 dark:text-red-100">
          The selected state event is not present in the backend-verified Store projection.
        </div>
      )}
      {activeSpan && activeTab === DiffTabOptions.FAILURES && (
        <div className="grow overflow-y-scroll border-t border-zinc-200 dark:border-zinc-700">
          <SpanFailuresList spans={[activeSpan]} />
        </div>
      )}
      {activeSpan && activeTab === DiffTabOptions.SPAN_DETAILS && (
        <div className="grow overflow-y-scroll border-t border-zinc-200 dark:border-zinc-700 p-4">
          <SpanAttributesContent span={activeSpan} origin="workflows" workflowSpanId={defaultWorkflowSpan.span_id} />
        </div>
      )}
      {stateViewsAvailable && STATE_TABS.has(activeTab) && (
        <div className="workflow-logs-json-container grow overflow-y-scroll border-t border-zinc-200 dark:border-zinc-700">
          <JsonView
            key={JSON.stringify(getTabJsonData(activeTab))}
            value={getTabJsonData(activeTab)}
            collapsed={getTabCollapsedLevel(activeTab)}
            shouldExpandNodeInitially={(isExpanded, { value, level }) => {
              const isArray = Array.isArray(value)
              if (isArray && level > 1 && Object.keys(value).length > 1) return true
              return isExpanded
            }}
            style={{ ...displayTheme, fontFamily: 'var(--font-mono)' }}
          >
            <JsonView.Quote>&#8203;</JsonView.Quote>
            <JsonView.Arrow>
              <TriangleDownIcon className="size-4 leading-0" />
            </JsonView.Arrow>
          </JsonView>
        </div>
      )}
    </div>
  )
}
