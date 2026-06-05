import { create } from 'zustand'

interface CompareStore {
  ids: string[]
  toggle: (id: string) => void
  isInCompare: (id: string) => boolean
  clear: () => void
}

export const useCompareStore = create<CompareStore>()((set, get) => ({
  ids: [],

  toggle: (id: string) => {
    set((state) => {
      if (state.ids.includes(id)) {
        return { ids: state.ids.filter((i) => i !== id) }
      }
      if (state.ids.length >= 3) return state
      return { ids: [...state.ids, id] }
    })
  },

  isInCompare: (id: string) => get().ids.includes(id),

  clear: () => set({ ids: [] }),
}))
