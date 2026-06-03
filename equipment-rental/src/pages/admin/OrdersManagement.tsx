import React, { useEffect, useState } from 'react'
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

const STATUS_TABS = [
  { value: 'all', label: 'Все' },
  { value: 'pending', label: 'Ожидают' },
  { value: 'confirmed', label: 'Подтверждённые' },
  { value: 'active', label: 'Активные' },
  { value: 'completed', label: 'Завершённые' },
  { value: 'cancelled', label: 'Отменённые' },
]

const STATUS_OPTIONS = [
  { value: 'pending', label: 'Ожидает' },
  { value: 'confirmed', label: 'Подтверждён' },
  { value: 'active', label: 'Активный' },
  { value: 'completed', label: 'Завершён' },
  { value: 'cancelled', label: 'Отменён' },
]

export const OrdersManagement: React.FC = () => {
  const { orders, updateOrderStatus } = useAdminStore()
  const [tab, setTab] = useState('all')
  const [search, setSearch] = useState('')
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null)

  useEffect(() => {
    document.title = 'Управление заказами — Админ'
  }, [])

  const filtered = orders.filter((o) => {
    if (tab !== 'all' && o.status !== tab) return false
    if (search) {
      const q = search.toLowerCase()
      return (
        o.clientName.toLowerCase().includes(q) ||
        o.id.toLowerCase().includes(q) ||
        o.equipmentName.toLowerCase().includes(q) ||
        (o.clientCompany || '').toLowerCase().includes(q)
      )
    }
    return true
  })

  const tabCount = (status: string) =>
    status === 'all' ? orders.length : orders.filter((o) => o.status === status).length

  return (
    <div className="p-6 lg:p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-black text-white">Управление заказами</h1>
        <p className="text-gray-500 text-sm">Всего заявок: {orders.length}</p>
      </div>

      {/* Status tabs */}
      <div className="flex gap-1 mb-6 overflow-x-auto">
        {STATUS_TABS.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-all cursor-pointer flex items-center gap-2 ${
              tab === value
                ? 'bg-blue-500/15 text-blue-400 border border-blue-500/30'
                : 'bg-gray-900 border border-gray-700/50 text-gray-500 hover:border-gray-600'
            }`}
          >
            {label}
            <span className={`text-xs px-1.5 py-0.5 rounded-full ${tab === value ? 'bg-blue-500/30 text-blue-300' : 'bg-gray-800 text-gray-600'}`}>
              {tabCount(value)}
            </span>
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="relative mb-5 max-w-sm">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по клиенту, ID, технике..."
          className="w-full bg-gray-900 border border-gray-700 text-gray-100 rounded-lg pl-9 pr-4 py-2.5 text-sm outline-none focus:border-blue-500 transition placeholder:text-gray-600"
        />
      </div>

      {/* Table */}
      <div className="bg-gray-900 border border-gray-700/50 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
                <th className="text-left px-5 py-3">ID / Дата</th>
                <th className="text-left px-5 py-3">Клиент</th>
                <th className="text-left px-5 py-3 hidden lg:table-cell">Техника</th>
                <th className="text-left px-5 py-3 hidden md:table-cell">Период</th>
                <th className="text-left px-5 py-3 hidden lg:table-cell">Сумма</th>
                <th className="text-left px-5 py-3">Статус</th>
                <th className="text-right px-5 py-3">Действия</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((order) => (
                <tr key={order.id} className="border-b border-gray-800/50 last:border-0 hover:bg-gray-800/20 transition-colors">
                  <td className="px-5 py-3">
                    <div className="text-xs font-mono text-blue-400">{order.id}</div>
                    <div className="text-xs text-gray-600">{formatDate(order.createdAt)}</div>
                  </td>
                  <td className="px-5 py-3">
                    <div className="text-sm font-medium text-gray-300">{order.clientName}</div>
                    {order.clientCompany && (
                      <div className="text-xs text-gray-600">{order.clientCompany}</div>
                    )}
                  </td>
                  <td className="px-5 py-3 hidden lg:table-cell">
                    <div className="text-sm text-gray-400 max-w-40 truncate">{order.equipmentName}</div>
                  </td>
                  <td className="px-5 py-3 hidden md:table-cell">
                    <div className="text-xs text-gray-500">
                      {formatDate(order.startDate)} – {formatDate(order.endDate)}
                    </div>
                  </td>
                  <td className="px-5 py-3 hidden lg:table-cell">
                    <span className="text-sm font-bold text-blue-400">{formatPrice(order.totalPrice)} ₽</span>
                  </td>
                  <td className="px-5 py-3">
                    <select
                      value={order.status}
                      onChange={(e) => updateOrderStatus(order.id, e.target.value as Order['status'])}
                      className="bg-gray-800 border border-gray-700 text-gray-300 rounded-md px-2 py-1 text-xs outline-none cursor-pointer focus:border-blue-500 transition"
                    >
                      {STATUS_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex justify-end">
                      <button
                        onClick={() => setSelectedOrder(order)}
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
            <div className="text-center py-10 text-gray-600">Заявок нет</div>
          )}
        </div>
      </div>

      {/* Order Detail Modal */}
      {selectedOrder && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg">
            <div className="flex items-center justify-between p-5 border-b border-gray-800">
              <div>
                <h2 className="font-bold text-gray-200">Заявка {selectedOrder.id}</h2>
                <Badge variant={selectedOrder.status as Order['status']}>
                  {statusLabels[selectedOrder.status]}
                </Badge>
              </div>
              <button onClick={() => setSelectedOrder(null)} className="text-gray-500 hover:text-gray-300 cursor-pointer">
                <X size={20} />
              </button>
            </div>
            <div className="p-5 space-y-3">
              {[
                { label: 'Клиент', value: selectedOrder.clientName },
                selectedOrder.clientCompany && { label: 'Компания', value: selectedOrder.clientCompany },
                { label: 'Email', value: selectedOrder.clientEmail },
                { label: 'Телефон', value: selectedOrder.clientPhone },
                { label: 'Техника', value: selectedOrder.equipmentName },
                { label: 'Начало', value: formatDate(selectedOrder.startDate) },
                { label: 'Окончание', value: formatDate(selectedOrder.endDate) },
                { label: 'Создана', value: formatDate(selectedOrder.createdAt) },
                selectedOrder.notes && { label: 'Примечания', value: selectedOrder.notes },
              ].filter(Boolean).map((item) => {
                const i = item as { label: string; value: string }
                return (
                  <div key={i.label} className="flex gap-4">
                    <span className="text-gray-500 text-sm w-28 shrink-0">{i.label}:</span>
                    <span className="text-gray-300 text-sm">{i.value}</span>
                  </div>
                )
              })}
              <div className="border-t border-gray-800 pt-3">
                <div className="flex justify-between">
                  <span className="text-gray-400 font-medium">Итого:</span>
                  <span className="text-xl font-black text-blue-400">
                    {formatPrice(selectedOrder.totalPrice)} ₽
                  </span>
                </div>
              </div>
            </div>
            <div className="p-5 border-t border-gray-800 flex justify-end">
              <Button variant="ghost" onClick={() => setSelectedOrder(null)}>Закрыть</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
