import { create } from 'zustand'

interface QuickViewStore {
  equipmentId: string | null
  open: (id: string) => void
  close: () => void
}

export const useQuickViewStore = create<QuickViewStore>()((set) => ({
  equipmentId: null,

  open: (id: string) => set({ equipmentId: id }),

  close: () => set({ equipmentId: null }),
}))
