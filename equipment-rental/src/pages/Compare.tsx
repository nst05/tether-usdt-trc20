import React, { useEffect } from 'react'
import { PageTransition } from '../components/PageTransition'
import { Link } from 'react-router-dom'
import { GitCompare, X, Star, MapPin } from 'lucide-react'
import { equipmentData } from '../data/equipment'
import { useCompareStore } from '../store/compareStore'
import { Badge, statusLabels } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { useCartStore } from '../store/cartStore'

function formatPrice(p: number) {
  return new Intl.NumberFormat('ru-RU').format(p)
}

export const Compare: React.FC = () => {
  const { ids, toggle, clear } = useCompareStore()
  const { addItem, items } = useCartStore()

  useEffect(() => {
    document.title = 'Сравнение техники — ТЕХПРОКАТ'
  }, [])

  const compareItems = ids
    .map((id) => equipmentData.find((e) => e.id === id))
    .filter((e): e is NonNullable<typeof e> => e !== undefined)

  const today = new Date()
  const nextWeek = new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000)
  const startDate = today.toISOString().split('T')[0]
  const endDate = nextWeek.toISOString().split('T')[0]

  const allSpecKeys = Array.from(
    new Set(compareItems.flatMap((e) => Object.keys(e.specs)))
  )

  return (
    <PageTransition>
      <div className="min-h-screen pt-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="mb-8 flex items-center justify-between flex-wrap gap-4">
            <div>
              <h1 className="text-3xl font-black text-white mb-2 flex items-center gap-3">
                <GitCompare size={28} className="text-amber-400" />
                Сравнение техники
              </h1>
              {compareItems.length > 0 && (
                <p className="text-gray-500">
                  Выбрано:{' '}
                  <span className="text-amber-400 font-medium">{compareItems.length}</span> единицы
                </p>
              )}
            </div>
            {compareItems.length > 0 && (
              <button
                onClick={clear}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-gray-400 border border-white/10 hover:border-white/20 hover:text-white transition-all cursor-pointer"
              >
                <X size={14} />
                Очистить всё
              </button>
            )}
          </div>

          {compareItems.length < 2 ? (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="w-20 h-20 rounded-full bg-amber-500/10 flex items-center justify-center mb-6">
                <GitCompare size={36} className="text-amber-400/50" />
              </div>
              <h2 className="text-xl font-bold text-gray-300 mb-2">
                Добавьте минимум 2 единицы техники для сравнения
              </h2>
              <p className="text-gray-600 mb-6 max-w-sm">
                Используйте кнопку «Сравнить» на карточках техники
              </p>
              <Link
                to="/catalog"
                className="inline-flex items-center gap-2 px-6 py-3 bg-amber-500 text-black font-bold rounded-lg hover:bg-amber-400 transition-colors"
              >
                Перейти в каталог
              </Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <th className="text-left p-4 w-40 text-xs text-gray-600 uppercase tracking-wider font-medium align-bottom">
                      Характеристика
                    </th>
                    {compareItems.map((eq) => (
                      <th key={eq.id} className="p-4 min-w-[220px] align-top">
                        <div className="bg-[#111111] border border-white/8 rounded-xl overflow-hidden relative">
                          <button
                            onClick={() => toggle(eq.id)}
                            className="absolute top-2 right-2 z-10 w-7 h-7 bg-black/70 backdrop-blur-sm rounded-full flex items-center justify-center border border-white/10 hover:border-red-500/40 hover:text-red-400 text-gray-500 transition-all cursor-pointer"
                            title="Убрать из сравнения"
                          >
                            <X size={12} />
                          </button>
                          <img
                            src={eq.image}
                            alt={eq.name}
                            className="w-full h-40 object-cover"
                          />
                          <div className="p-3">
                            <h3 className="text-sm font-bold text-white mb-1 text-left line-clamp-2">
                              {eq.name}
                            </h3>
                            <div className="flex items-center gap-1 mb-2">
                              <MapPin size={10} className="text-gray-600" />
                              <span className="text-xs text-gray-600">{eq.location}</span>
                            </div>
                            <div className="flex items-center gap-1 mb-2">
                              {Array.from({ length: 5 }).map((_, i) => (
                                <Star
                                  key={i}
                                  size={10}
                                  className={i < Math.floor(eq.rating) ? 'text-amber-400 fill-amber-400' : 'text-gray-700'}
                                />
                              ))}
                              <span className="text-xs text-gray-400 ml-0.5">{eq.rating.toFixed(1)}</span>
                            </div>
                            <div className="mb-3">
                              <Badge variant={eq.availability as 'available' | 'rented' | 'maintenance'}>
                                {statusLabels[eq.availability]}
                              </Badge>
                            </div>
                            <div className="text-xl font-black text-amber-400 mb-3 text-left">
                              {formatPrice(eq.pricePerDay)}
                              <span className="text-xs text-gray-500 font-normal ml-1">₽/день</span>
                            </div>
                            <div className="flex flex-col gap-1.5">
                              <Link to={`/catalog/${eq.id}`} className="block">
                                <Button variant="secondary" size="sm" className="w-full text-xs">
                                  Подробнее
                                </Button>
                              </Link>
                              <Button
                                variant="primary"
                                size="sm"
                                className="w-full text-xs"
                                disabled={eq.availability !== 'available' || items.some((i) => i.equipment.id === eq.id)}
                                onClick={() => {
                                  if (eq.availability === 'available' && !items.some((i) => i.equipment.id === eq.id)) {
                                    addItem(eq, startDate, endDate)
                                  }
                                }}
                              >
                                {items.some((i) => i.equipment.id === eq.id) ? 'В корзине' : 'В корзину'}
                              </Button>
                            </div>
                          </div>
                        </div>
                      </th>
                    ))}
                    {Array.from({ length: 3 - compareItems.length }).map((_, i) => (
                      <th key={`empty-${i}`} className="p-4 min-w-[220px]">
                        <div className="bg-[#111111]/50 border border-dashed border-white/10 rounded-xl h-full min-h-[300px] flex flex-col items-center justify-center gap-3">
                          <GitCompare size={24} className="text-gray-700" />
                          <span className="text-xs text-gray-700">Добавьте из каталога</span>
                          <Link
                            to="/catalog"
                            className="text-xs text-amber-500 hover:text-amber-400 underline transition-colors"
                          >
                            Перейти
                          </Link>
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  <tr className="border-t border-white/5">
                    <td className="p-4 text-xs text-gray-600 uppercase tracking-wider font-medium whitespace-nowrap">
                      Цена / неделя
                    </td>
                    {compareItems.map((eq) => (
                      <td key={eq.id} className="p-4 text-center text-sm text-gray-300">
                        {formatPrice(eq.pricePerWeek)} ₽
                      </td>
                    ))}
                    {Array.from({ length: 3 - compareItems.length }).map((_, i) => (
                      <td key={`empty-week-${i}`} className="p-4" />
                    ))}
                  </tr>
                  <tr className="border-t border-white/5">
                    <td className="p-4 text-xs text-gray-600 uppercase tracking-wider font-medium whitespace-nowrap">
                      Цена / месяц
                    </td>
                    {compareItems.map((eq) => (
                      <td key={eq.id} className="p-4 text-center text-sm text-gray-300">
                        {formatPrice(eq.pricePerMonth)} ₽
                      </td>
                    ))}
                    {Array.from({ length: 3 - compareItems.length }).map((_, i) => (
                      <td key={`empty-month-${i}`} className="p-4" />
                    ))}
                  </tr>
                  <tr className="border-t border-white/5">
                    <td className="p-4 text-xs text-gray-600 uppercase tracking-wider font-medium whitespace-nowrap">
                      Масса
                    </td>
                    {compareItems.map((eq) => (
                      <td key={eq.id} className="p-4 text-center text-sm text-gray-300">
                        {eq.weight} т
                      </td>
                    ))}
                    {Array.from({ length: 3 - compareItems.length }).map((_, i) => (
                      <td key={`empty-weight-${i}`} className="p-4" />
                    ))}
                  </tr>
                  <tr className="border-t border-white/5">
                    <td className="p-4 text-xs text-gray-600 uppercase tracking-wider font-medium whitespace-nowrap">
                      Мощность
                    </td>
                    {compareItems.map((eq) => (
                      <td key={eq.id} className="p-4 text-center text-sm text-gray-300">
                        {eq.power}
                      </td>
                    ))}
                    {Array.from({ length: 3 - compareItems.length }).map((_, i) => (
                      <td key={`empty-power-${i}`} className="p-4" />
                    ))}
                  </tr>
                  {allSpecKeys.map((key, rowIdx) => (
                    <tr key={key} className={`border-t border-white/5 ${rowIdx % 2 === 0 ? 'bg-white/[0.015]' : ''}`}>
                      <td className="p-4 text-xs text-gray-600 uppercase tracking-wider font-medium whitespace-nowrap">
                        {key}
                      </td>
                      {compareItems.map((eq) => (
                        <td key={eq.id} className="p-4 text-center text-sm text-gray-300">
                          {eq.specs[key] ?? <span className="text-gray-700">—</span>}
                        </td>
                      ))}
                      {Array.from({ length: 3 - compareItems.length }).map((_, i) => (
                        <td key={`empty-spec-${key}-${i}`} className="p-4" />
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </PageTransition>
  )
}
