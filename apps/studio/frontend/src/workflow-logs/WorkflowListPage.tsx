import WorkflowList from './WorkflowList'

/**
 * Workflow List Page
 *
 * Lists the workflow runs that have taken place.
 * @returns
 */
export default function WorkflowListPage() {
  return (
    <div className={'p-5'}>
      <h1>workflow logs</h1>
      <div className="h-2"></div>
      <WorkflowList />
    </div>
  )
}
