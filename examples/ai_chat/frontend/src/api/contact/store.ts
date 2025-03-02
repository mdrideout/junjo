import { create } from 'zustand'
import { ContactRead } from './schemas'
import { devtools } from 'zustand/middleware'
import { useMemo } from 'react'

interface ContactState {
  contact: Partial<{ [id: string]: ContactRead }>

  upsertContacts: (list: ContactRead[]) => void
  deleteContact: (id: string) => void
}

export const useContactStore = create<ContactState>()(
  devtools((set) => ({
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
)

// Selector for sorted contacts
export const useSortedContacts = () => {
  const contacts = useContactStore((state) => state.contact)

  // useMemo to prevent recalculation if contacts haven't changed
  return useMemo(() => {
    return Object.values(contacts)
      .filter((contact): contact is ContactRead => contact !== undefined) // Filter out undefined values and ensure type safety
      .sort((a, b) => {
        // Handle potential undefined updated_at
        const dateA = a.updated_at ? new Date(a.updated_at) : new Date(0) // Default to a very old date if undefined
        const dateB = b.updated_at ? new Date(b.updated_at) : new Date(0)
        return dateB.getTime() - dateA.getTime() // Sort in descending order (most recent first)
      })
  }, [contacts])
}
