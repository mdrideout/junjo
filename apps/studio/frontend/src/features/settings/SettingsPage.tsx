import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { RootState } from '../../root-store/store'
import { SettingsStateActions } from './slice'

export default function SettingsPage() {
  const dispatch = useAppDispatch()
  const { flushWalLoading, flushWalError, flushWalSuccess, lastFlushTime } = useAppSelector(
    (state: RootState) => state.settingsState,
  )

  const handleFlushWal = () => {
    if (confirm('Are you sure you want to flush the WAL to Parquet files?')) {
      dispatch(SettingsStateActions.flushWal())
    }
  }

  // Format last flush time
  const lastFlushTimeString = lastFlushTime ? new Date(lastFlushTime).toLocaleString() : 'Never'

  return (
    <div className={'px-3 py-4 flex flex-col h-dvh overflow-y-auto'}>
      <div className={'flex gap-x-3 px-2 items-center'}>
        <div className={'flex gap-x-3 font-bold'}>Settings</div>
      </div>
      <hr className={'my-4'} />

      {/* System Operations Section */}
      <div className={'px-2'}>
        <h2 className={'text-sm font-semibold mb-4'}>System Operations</h2>

        {/* Flush WAL Card */}
        <div className={'border border-zinc-200 dark:border-zinc-700 rounded-lg p-4 max-w-md'}>
          <h3 className={'font-medium mb-2'}>Flush WAL to Parquet</h3>
          <p className={'text-sm text-zinc-500 dark:text-zinc-400 mb-4'}>
            Immediately flush pending spans from the Write-Ahead Log (WAL) to Parquet files. This is normally done
            automatically by the ingestion service.
          </p>

          {/* Status Messages */}
          {flushWalError && (
            <div className={'text-sm text-red-600 dark:text-red-400 mb-3 p-2 bg-red-50 dark:bg-red-900/20 rounded'}>
              Error: {flushWalError}
            </div>
          )}
          {flushWalSuccess && (
            <div
              className={'text-sm text-green-600 dark:text-green-400 mb-3 p-2 bg-green-50 dark:bg-green-900/20 rounded'}
            >
              WAL flushed successfully
            </div>
          )}

          <div className={'flex items-center justify-between'}>
            <button
              className={
                'px-3 py-1.5 text-sm font-medium rounded-md cursor-pointer ' +
                'bg-zinc-200 hover:bg-zinc-300 dark:bg-zinc-700 dark:hover:bg-zinc-600 ' +
                'disabled:opacity-50 disabled:cursor-not-allowed'
              }
              onClick={handleFlushWal}
              disabled={flushWalLoading}
            >
              {flushWalLoading ? 'Flushing...' : 'Flush WAL'}
            </button>

            <span className={'text-xs text-zinc-400 dark:text-zinc-500'}>Last flush: {lastFlushTimeString}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
