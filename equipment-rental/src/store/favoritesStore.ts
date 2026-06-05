import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface FavoritesStore {
  ids: string[]
  toggle: (id: string) => void
  isFavorite: (id: string) => boolean
}

export const useFavoritesStore = create<FavoritesStore>()(
  persist(
    (set, get) => ({
      ids: [],

      toggle: (id: string) => {
        set((state) => ({
          ids: state.ids.includes(id)
            ? state.ids.filter((i) => i !== id)
            : [...state.ids, id],
        }))
      },

      isFavorite: (id: string) => get().ids.includes(id),
    }),
    {
      name: 'tehprokat-favorites',
    }
  )
)
