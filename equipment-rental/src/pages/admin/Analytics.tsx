import React, { useEffect } from 'react'

function formatPrice(p: number) {
  return new Intl.NumberFormat('ru-RU').format(p)
}

const MONTHS = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']

const monthlyRevenue = [1200000, 980000, 1450000, 1680000, 2100000, 1890000, 2340000, 2560000, 1970000, 2180000, 2450000, 2890000]
const maxMonthly = Math.max(...monthlyRevenue)

const utilizationData = [
  { name: 'Экскаваторы', value: 78, color: '#F59E0B' },
  { name: 'Краны', value: 65, color: '#3B82F6' },
  { name: 'Бульдозеры', value: 82, color: '#10B981' },
  { name: 'Погрузчики', value: 91, color: '#8B5CF6' },
  { name: 'Дорожная', value: 55, color: '#EF4444' },
  { name: 'Буровая', value: 44, color: '#F97316' },
]

const categoryRevShare = [
  { name: 'Краны', pct: 35, color: '#3B82F6' },
  { name: 'Экскаваторы', pct: 28, color: '#F59E0B' },
  { name: 'Буровая', pct: 15, color: '#F97316' },
  { name: 'Дорожная', pct: 12, color: '#EF4444' },
  { name: 'Бульдозеры', pct: 7, color: '#10B981' },
  { name: 'Погрузчики', pct: 3, color: '#8B5CF6' },
]

const metrics = [
  { label: 'Средний чек аренды', value: '485 000 ₽', delta: '+8.2%', up: true },
  { label: 'Длительность аренды (ср.)', value: '18.4 дня', delta: '+2.1 дня', up: true },
  { label: 'Коэффициент использования', value: '72%', delta: '+5%', up: true },
  { label: 'Повторные клиенты', value: '64%', delta: '+3%', up: true },
  { label: 'Отменённые заявки', value: '4.2%', delta: '-1.1%', up: false },
  { label: 'Средний NPS', value: '74', delta: '+6', up: true },
]

export const Analytics: React.FC = () => {
  useEffect(() => {
    document.title = 'Аналитика — Админ'
  }, [])

  return (
    <div className="p-6 lg:p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-black text-white">Аналитика</h1>
        <p className="text-gray-500 text-sm">Сводные показатели работы парка</p>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        {metrics.map(({ label, value, delta, up }) => (
          <div key={label} className="bg-gray-900 border border-gray-700/50 rounded-xl p-4">
            <div className="text-xs text-gray-500 mb-2">{label}</div>
            <div className="text-2xl font-black text-white mb-1">{value}</div>
            <div className={`text-xs font-medium ${up ? 'text-emerald-400' : 'text-red-400'}`}>
              {delta} vs прошлый период
            </div>
          </div>
        ))}
      </div>

      {/* Revenue chart */}
      <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-6 mb-6">
        <h2 className="font-bold text-gray-200 mb-6">Выручка по месяцам (текущий год), ₽</h2>
        <div className="relative">
          {/* Y-axis labels */}
          <div className="flex">
            <div className="w-16 shrink-0 flex flex-col justify-between h-48 text-right pr-3">
              {[3000, 2000, 1000, 0].map((v) => (
                <div key={v} className="text-xs text-gray-600">{v}к</div>
              ))}
            </div>
            {/* Chart area */}
            <div className="flex-1 relative">
              {/* Grid lines */}
              {[0, 25, 50, 75, 100].map((p) => (
                <div
                  key={p}
                  className="absolute w-full border-t border-gray-800/50"
                  style={{ bottom: `${p}%` }}
                />
              ))}
              {/* Bars and line */}
              <div className="flex items-end gap-1 h-48 relative z-10">
                {monthlyRevenue.map((value, i) => {
                  const heightPct = (value / maxMonthly) * 100
                  return (
                    <div key={i} className="flex-1 flex flex-col items-center gap-1 group">
                      <div className="text-xs text-gray-700 group-hover:text-blue-400 transition-colors opacity-0 group-hover:opacity-100">
                        {formatPrice(value / 1000)}к
                      </div>
                      <div
                        className="w-full bg-gradient-to-t from-blue-600 to-amber-400 rounded-t hover:from-blue-500 hover:to-amber-300 transition-colors cursor-default"
                        style={{ height: `${heightPct * 0.85}%` }}
                        title={`${MONTHS[i]}: ${formatPrice(value)} ₽`}
                      />
                      <div className="text-xs text-gray-600">{MONTHS[i]}</div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Utilization */}
        <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-6">
          <h2 className="font-bold text-gray-200 mb-6">Загрузка парка по категориям, %</h2>
          <div className="space-y-4">
            {utilizationData.map(({ name, value, color }) => (
              <div key={name}>
                <div className="flex justify-between text-sm mb-1.5">
                  <span className="text-gray-400">{name}</span>
                  <span className="font-bold" style={{ color }}>{value}%</span>
                </div>
                <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${value}%`, backgroundColor: color }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Category pie */}
        <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-6">
          <h2 className="font-bold text-gray-200 mb-6">Выручка по категориям</h2>
          {/* CSS pie via stacked segments */}
          <div className="flex items-center gap-6">
            <div className="relative w-40 h-40 shrink-0">
              <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                {(() => {
                  let offset = 0
                  return categoryRevShare.map(({ name, pct, color }) => {
                    const el = (
                      <circle
                        key={name}
                        cx="18" cy="18" r="15.9155"
                        fill="none"
                        stroke={color}
                        strokeWidth="3.5"
                        strokeDasharray={`${pct} ${100 - pct}`}
                        strokeDashoffset={`-${offset}`}
                      />
                    )
                    offset += pct
                    return el
                  })
                })()}
              </svg>
            </div>
            <div className="space-y-2 flex-1">
              {categoryRevShare.map(({ name, pct, color }) => (
                <div key={name} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                    <span className="text-sm text-gray-400">{name}</span>
                  </div>
                  <span className="text-sm font-bold" style={{ color }}>{pct}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
