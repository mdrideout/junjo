import type { StoreBoundaryDetail, StoreDetail, StoreTransition } from './schemas/store-diagnostics'

/** Reuse physical events while selecting one execution's observed Store interval. */
export function hydrateStoreView(
  view: StoreBoundaryDetail | undefined,
  transitions: readonly StoreTransition[] = [],
): StoreDetail | null {
  if (view === undefined) return null
  return {
    ...view,
    transitions: transitions
      .filter((item) => view.sequence_start !== null && view.sequence_end !== null &&
        view.sequence_start < item.sequence && item.sequence <= view.sequence_end)
      .map((item) => view.reconstructable ? item : { ...item, before: null, after: null }),
  }
}
