import React, { useEffect, useState, useMemo } from 'react'
import { Search, Eye, X } from 'lucide-react'
import { useAdminStore } from '../../store/adminStore'
import { Badge, statusLabels } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Order } from '../../types'

function formatPrice(p: number) {
  return new Intl.NumberFormat('ru-RU').format(p)
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('ru-RU')
}

interface ClientSummary {
  id: string
  name: string
  email: string
  phone: string
  company?: string
  orders: Order[]
  totalSpent: number
  firstOrder: string
}

export const ClientsManagement: React.FC = () => {
  const { orders } = useAdminStore()
  const [search, setSearch] = useState('')
  const [selectedClient, setSelectedClient] = useState<ClientSummary | null>(null)

  useEffect(() => {
    document.title = 'Клиенты — Админ'
  }, [])

  const clients = useMemo<ClientSummary[]>(() => {
    const map = new Map<string, ClientSummary>()
    orders.forEach((o) => {
      const key = o.clientEmail
      if (!map.has(key)) {
        map.set(key, {
          id: key,
          name: o.clientName,
          email: o.clientEmail,
          phone: o.clientPhone,
          company: o.clientCompany,
          orders: [],
          totalSpent: 0,
          firstOrder: o.createdAt,
        })
      }
      const client = map.get(key)!
      client.orders.push(o)
      client.totalSpent += o.totalPrice
      if (o.createdAt < client.firstOrder) client.firstOrder = o.createdAt
    })
    return Array.from(map.values()).sort((a, b) => b.totalSpent - a.totalSpent)
  }, [orders])

  const filtered = clients.filter((c) => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      c.name.toLowerCase().includes(q) ||
      c.email.toLowerCase().includes(q) ||
      (c.company || '').toLowerCase().includes(q)
    )
  })

  return (
    <div className="p-6 lg:p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-black text-white">Клиенты</h1>
        <p className="text-gray-500 text-sm">Уникальных клиентов: {clients.length}</p>
      </div>

      <div className="relative mb-5 max-w-sm">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по имени, email, компании..."
          className="w-full bg-gray-900 border border-gray-700 text-gray-100 rounded-lg pl-9 pr-4 py-2.5 text-sm outline-none focus:border-blue-500 transition placeholder:text-gray-600"
        />
      </div>

      <div className="bg-gray-900 border border-gray-700/50 rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
              <th className="text-left px-5 py-3">Клиент</th>
              <th className="text-left px-5 py-3 hidden md:table-cell">Компания</th>
              <th className="text-left px-5 py-3 hidden lg:table-cell">Заказов</th>
              <th className="text-left px-5 py-3 hidden lg:table-cell">Потрачено</th>
              <th className="text-left px-5 py-3 hidden md:table-cell">Клиент с</th>
              <th className="text-right px-5 py-3">Действия</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((client) => (
              <tr key={client.id} className="border-b border-gray-800/50 last:border-0 hover:bg-gray-800/20 transition-colors">
                <td className="px-5 py-3">
                  <div className="font-medium text-gray-300 text-sm">{client.name}</div>
                  <div className="text-xs text-gray-600">{client.email}</div>
                </td>
                <td className="px-5 py-3 hidden md:table-cell">
                  <span className="text-sm text-gray-500">{client.company || '—'}</span>
                </td>
                <td className="px-5 py-3 hidden lg:table-cell">
                  <span className="text-sm font-medium text-gray-300">{client.orders.length}</span>
                </td>
                <td className="px-5 py-3 hidden lg:table-cell">
                  <span className="text-sm font-bold text-blue-400">{formatPrice(client.totalSpent)} ₽</span>
                </td>
                <td className="px-5 py-3 hidden md:table-cell">
                  <span className="text-xs text-gray-600">{formatDate(client.firstOrder)}</span>
                </td>
                <td className="px-5 py-3">
                  <div className="flex justify-end">
                    <button
                      onClick={() => setSelectedClient(client)}
                      className="p-1.5 text-gray-500 hover:text-blue-400 hover:bg-blue-500/10 rounded transition-all cursor-pointer"
                    >
                      <Eye size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="text-center py-10 text-gray-600">Клиентов нет</div>
        )}
      </div>

      {/* Client Detail Modal */}
      {selectedClient && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-5 border-b border-gray-800 sticky top-0 bg-gray-900">
              <h2 className="font-bold text-gray-200">{selectedClient.name}</h2>
              <button onClick={() => setSelectedClient(null)} className="text-gray-500 hover:text-gray-300 cursor-pointer">
                <X size={20} />
              </button>
            </div>
            <div className="p-5">
              <div className="grid grid-cols-2 gap-4 mb-6">
                {[
                  { label: 'Email', value: selectedClient.email },
                  { label: 'Телефон', value: selectedClient.phone },
                  { label: 'Компания', value: selectedClient.company || '—' },
                  { label: 'Заказов', value: String(selectedClient.orders.length) },
                  { label: 'Потрачено', value: formatPrice(selectedClient.totalSpent) + ' ₽' },
                  { label: 'Клиент с', value: formatDate(selectedClient.firstOrder) },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-gray-800/50 rounded-lg p-3">
                    <div className="text-xs text-gray-500 mb-0.5">{label}</div>
                    <div className="text-sm text-gray-300 font-medium">{value}</div>
                  </div>
                ))}
              </div>

              <h3 className="font-bold text-gray-300 text-sm mb-3">История заказов</h3>
              <div className="space-y-2">
                {selectedClient.orders.map((order) => (
                  <div key={order.id} className="bg-gray-800/50 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-mono text-blue-400">{order.id}</span>
                      <Badge variant={order.status as Order['status']}>
                        {statusLabels[order.status]}
                      </Badge>
                    </div>
                    <div className="text-xs text-gray-400">{order.equipmentName}</div>
                    <div className="flex justify-between mt-1">
                      <span className="text-xs text-gray-600">
                        {formatDate(order.startDate)} – {formatDate(order.endDate)}
                      </span>
                      <span className="text-xs font-bold text-blue-400">
                        {formatPrice(order.totalPrice)} ₽
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="p-5 border-t border-gray-800">
              <Button variant="ghost" className="w-full" onClick={() => setSelectedClient(null)}>
                Закрыть
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
