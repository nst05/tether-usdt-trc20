import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { CartItem, Equipment } from '../types'

interface CartStore {
  items: CartItem[]
  addItem: (equipment: Equipment, startDate: string, endDate: string) => void
  removeItem: (equipmentId: string) => void
  clearCart: () => void
  getTotalPrice: () => number
  getTotalItems: () => number
}

function calculateDays(startDate: string, endDate: string): number {
  const start = new Date(startDate)
  const end = new Date(endDate)
  const diff = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24))
  return Math.max(1, diff)
}

function calculatePrice(equipment: Equipment, days: number): number {
  if (days >= 30) {
    const months = Math.floor(days / 30)
    const remainingDays = days % 30
    return months * equipment.pricePerMonth + remainingDays * equipment.pricePerDay
  } else if (days >= 7) {
    const weeks = Math.floor(days / 7)
    const remainingDays = days % 7
    return weeks * equipment.pricePerWeek + remainingDays * equipment.pricePerDay
  } else {
    return days * equipment.pricePerDay
  }
}

export const useCartStore = create<CartStore>()(
  persist(
    (set, get) => ({
      items: [],

      addItem: (equipment, startDate, endDate) => {
        const days = calculateDays(startDate, endDate)
        const totalPrice = calculatePrice(equipment, days)

        set((state) => {
          const existing = state.items.findIndex((i) => i.equipment.id === equipment.id)
          if (existing >= 0) {
            const updated = [...state.items]
            updated[existing] = { equipment, startDate, endDate, days, totalPrice }
            return { items: updated }
          }
          return {
            items: [...state.items, { equipment, startDate, endDate, days, totalPrice }],
          }
        })
      },

      removeItem: (equipmentId) => {
        set((state) => ({
          items: state.items.filter((i) => i.equipment.id !== equipmentId),
        }))
      },

      clearCart: () => set({ items: [] }),

      getTotalPrice: () => {
        return get().items.reduce((sum, item) => sum + item.totalPrice, 0)
      },

      getTotalItems: () => get().items.length,
    }),
    {
      name: 'equipment-cart',
    }
  )
)
