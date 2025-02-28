import { create } from 'zustand'
import { WorkflowMetadatum } from '../schemas'

interface WorkflowMetadataState {
  metadata: Partial<{ [ExecID: string]: WorkflowMetadatum }>

  setMetadata: (list: WorkflowMetadatum[]) => void
  upsertMetadata: (list: WorkflowMetadatum[]) => void
}

export const useMetadataStore = create<WorkflowMetadataState>()((set) => ({
  metadata: {},

  // Set metadata (replace existing data)
  setMetadata: (list) =>
    set(() => {
      const newMetadata: Partial<{ [ExecID: string]: WorkflowMetadatum }> = {}
      list.forEach((item) => {
        newMetadata[item.ExecID] = item
      })
      return { metadata: newMetadata }
    }),

  // Upsert metadata (add new data, overwrite existing data)
  upsertMetadata: (list) =>
    set((state) => {
      const newMetadata = { ...state.metadata }
      list.forEach((item) => {
        newMetadata[item.ExecID] = item
      })
      return { metadata: newMetadata }
    }),
}))
