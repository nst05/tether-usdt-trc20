import React, { useEffect } from 'react'
import { TrendingUp, Package, ClipboardList, Wrench, ArrowUp } from 'lucide-react'
import { useAdminStore } from '../../store/adminStore'
import { Badge, statusLabels } from '../../components/ui/Badge'
import { Link } from 'react-router-dom'

function formatPrice(p: number) {
  return new Intl.NumberFormat('ru-RU').format(p)
}

const revenueData = [
  { day: 'Пн', value: 420000 },
  { day: 'Вт', value: 580000 },
  { day: 'Ср', value: 320000 },
  { day: 'Чт', value: 890000 },
  { day: 'Пт', value: 750000 },
  { day: 'Сб', value: 440000 },
  { day: 'Вс', value: 290000 },
]

const maxRevenue = Math.max(...revenueData.map((d) => d.value))

export const Dashboard: React.FC = () => {
  const { orders, equipment } = useAdminStore()

  useEffect(() => {
    document.title = 'Дашборд — Админ ТЕХПРОКАТ'
  }, [])

  const activeOrders = orders.filter((o) => o.status === 'active').length
  const pendingOrders = orders.filter((o) => o.status === 'pending').length
  const monthRevenue = orders
    .filter((o) => ['active', 'completed', 'confirmed'].includes(o.status))
    .reduce((s, o) => s + o.totalPrice, 0)
  const maintenanceCount = equipment.filter((e) => e.availability === 'maintenance').length

  const availableCount = equipment.filter((e) => e.availability === 'available').length
  const rentedCount = equipment.filter((e) => e.availability === 'rented').length
  const total = equipment.length
  const availablePct = Math.round((availableCount / total) * 100)
  const rentedPct = Math.round((rentedCount / total) * 100)
  const maintenancePct = Math.round((maintenanceCount / total) * 100)

  const recentOrders = [...orders].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(0, 5)
  const topEquipment = equipment
    .map((e) => ({
      ...e,
      orderCount: orders.filter((o) => o.equipmentId === e.id).length,
    }))
    .sort((a, b) => b.orderCount - a.orderCount)
    .slice(0, 5)

  const kpis = [
    { label: 'Активных аренд', value: activeOrders, icon: Package, color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20', trend: '+3' },
    { label: 'Выручка (месяц)', value: formatPrice(monthRevenue) + ' ₽', icon: TrendingUp, color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/20', trend: '+12%' },
    { label: 'Новых заявок', value: pendingOrders, icon: ClipboardList, color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/20', trend: `+${pendingOrders}` },
    { label: 'На обслуживании', value: maintenanceCount, icon: Wrench, color: 'text-yellow-400', bg: 'bg-yellow-500/10 border-yellow-500/20', trend: '' },
  ]

  return (
    <div className="p-6 lg:p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-black text-white">Дашборд</h1>
        <p className="text-gray-500 text-sm">Обзор текущего состояния системы</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
        {kpis.map(({ label, value, icon: Icon, color, bg, trend }) => (
          <div key={label} className={`bg-gray-900 border ${bg} rounded-xl p-5`}>
            <div className="flex items-start justify-between mb-3">
              <Icon size={20} className={color} />
              {trend && (
                <span className="flex items-center gap-1 text-xs text-emerald-400 font-medium">
                  <ArrowUp size={10} />
                  {trend}
                </span>
              )}
            </div>
            <div className={`text-2xl font-black mb-1 ${color}`}>{value}</div>
            <div className="text-xs text-gray-500">{label}</div>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-6 mb-8">
        {/* Revenue chart */}
        <div className="lg:col-span-2 bg-gray-900 border border-gray-700/50 rounded-xl p-5">
          <h2 className="font-bold text-gray-200 mb-5">Выручка за 7 дней</h2>
          <div className="flex items-end gap-2 h-40">
            {revenueData.map(({ day, value }) => {
              const heightPct = (value / maxRevenue) * 100
              return (
                <div key={day} className="flex-1 flex flex-col items-center gap-2">
                  <div className="text-xs text-gray-600 font-medium">
                    {formatPrice(value / 1000)}к
                  </div>
                  <div className="w-full relative" style={{ height: `${Math.max(heightPct * 0.9, 5)}%` }}>
                    <div
                      className="absolute bottom-0 w-full bg-gradient-to-t from-blue-600 to-amber-400 rounded-t-sm hover:from-blue-500 hover:to-amber-300 transition-colors"
                      style={{ height: '100%' }}
                    />
                  </div>
                  <div className="text-xs text-gray-600">{day}</div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Donut chart */}
        <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-5">
          <h2 className="font-bold text-gray-200 mb-5">Статус парка</h2>
          {/* CSS Donut */}
          <div className="flex items-center justify-center mb-5">
            <div className="relative w-28 h-28">
              <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                <circle cx="18" cy="18" r="15.9155" fill="none" stroke="#1F2937" strokeWidth="3" />
                {/* Available */}
                <circle
                  cx="18" cy="18" r="15.9155"
                  fill="none"
                  stroke="#10B981"
                  strokeWidth="3"
                  strokeDasharray={`${availablePct} ${100 - availablePct}`}
                  strokeDashoffset="0"
                />
                {/* Rented */}
                <circle
                  cx="18" cy="18" r="15.9155"
                  fill="none"
                  stroke="#EF4444"
                  strokeWidth="3"
                  strokeDasharray={`${rentedPct} ${100 - rentedPct}`}
                  strokeDashoffset={`-${availablePct}`}
                />
                {/* Maintenance */}
                <circle
                  cx="18" cy="18" r="15.9155"
                  fill="none"
                  stroke="#F59E0B"
                  strokeWidth="3"
                  strokeDasharray={`${maintenancePct} ${100 - maintenancePct}`}
                  strokeDashoffset={`-${availablePct + rentedPct}`}
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="text-center">
                  <div className="text-lg font-black text-white">{total}</div>
                  <div className="text-xs text-gray-600">ед.</div>
                </div>
              </div>
            </div>
          </div>
          <div className="space-y-2">
            {[
              { label: 'Доступно', count: availableCount, color: 'bg-emerald-500' },
              { label: 'Арендовано', count: rentedCount, color: 'bg-red-500' },
              { label: 'Обслуживание', count: maintenanceCount, color: 'bg-blue-500' },
            ].map(({ label, count, color }) => (
              <div key={label} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <div className={`w-2.5 h-2.5 rounded-full ${color}`} />
                  <span className="text-gray-400">{label}</span>
                </div>
                <span className="text-gray-300 font-medium">{count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Recent orders */}
        <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold text-gray-200">Последние заявки</h2>
            <Link to="/admin/orders" className="text-xs text-blue-400 hover:underline">
              Все заявки
            </Link>
          </div>
          <div className="space-y-3">
            {recentOrders.map((order) => (
              <div key={order.id} className="flex items-center justify-between gap-3 py-2 border-b border-gray-800/50 last:border-0">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-300 truncate">{order.clientName}</div>
                  <div className="text-xs text-gray-600 truncate">{order.equipmentName}</div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant={order.status as 'pending' | 'confirmed' | 'active' | 'completed' | 'cancelled'}>
                    {statusLabels[order.status]}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Top rented */}
        <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold text-gray-200">Топ техники</h2>
            <Link to="/admin/equipment" className="text-xs text-blue-400 hover:underline">
              Весь парк
            </Link>
          </div>
          <div className="space-y-3">
            {topEquipment.map((eq, i) => (
              <div key={eq.id} className="flex items-center gap-3">
                <div className="w-6 h-6 rounded-full bg-gray-800 flex items-center justify-center text-xs font-bold text-gray-500">
                  {i + 1}
                </div>
                <img src={eq.image} alt={eq.name} className="w-10 h-8 object-cover rounded" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-gray-300 truncate">{eq.name}</div>
                  <div className="text-xs text-gray-600">{eq.orderCount} заказов</div>
                </div>
                <div className="text-xs text-blue-400 font-medium shrink-0">
                  {formatPrice(eq.pricePerDay)} ₽/д
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
