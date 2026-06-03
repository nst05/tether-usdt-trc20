import { create } from 'zustand'
import { Equipment, Order } from '../types'
import { equipmentData } from '../data/equipment'
import { ordersData } from '../data/orders'

interface AdminStore {
  equipment: Equipment[]
  orders: Order[]
  updateEquipmentStatus: (id: string, status: Equipment['availability']) => void
  updateOrderStatus: (id: string, status: Order['status']) => void
  addEquipment: (equipment: Equipment) => void
  deleteEquipment: (id: string) => void
  updateEquipment: (id: string, updates: Partial<Equipment>) => void
}

export const useAdminStore = create<AdminStore>()((set) => ({
  equipment: equipmentData,
  orders: ordersData,

  updateEquipmentStatus: (id, status) => {
    set((state) => ({
      equipment: state.equipment.map((e) =>
        e.id === id ? { ...e, availability: status } : e
      ),
    }))
  },

  updateOrderStatus: (id, status) => {
    set((state) => ({
      orders: state.orders.map((o) =>
        o.id === id ? { ...o, status } : o
      ),
    }))
  },

  addEquipment: (equipment) => {
    set((state) => ({
      equipment: [...state.equipment, equipment],
    }))
  },

  deleteEquipment: (id) => {
    set((state) => ({
      equipment: state.equipment.filter((e) => e.id !== id),
    }))
  },

  updateEquipment: (id, updates) => {
    set((state) => ({
      equipment: state.equipment.map((e) =>
        e.id === id ? { ...e, ...updates } : e
      ),
    }))
  },
}))
