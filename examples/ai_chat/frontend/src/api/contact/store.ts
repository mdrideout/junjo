import { create } from 'zustand'
import { ContactRead } from './schemas'

interface ContactState {
  contact: Partial<{ [id: string]: ContactRead }>

  upsertContacts: (list: ContactRead[]) => void
  deleteContact: (id: string) => void
}

export const useContactStore = create<ContactState>()((set) => ({
  contact: {},

  upsertContacts: (list: ContactRead[]) =>
    set((state) => {
      const newContacts = { ...state.contact }
      list.forEach((item) => {
        newContacts[item.id] = item
      })
      return { contact: newContacts }
    }),

  deleteContact: (id: string) =>
    set((state) => {
      const newContacts = { ...state.contact }
      delete newContacts[id]
      return { contact: newContacts }
    }),
}))
