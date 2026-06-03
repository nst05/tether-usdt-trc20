import React, { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Star, MapPin, ChevronRight, ShoppingCart, Phone, CheckCircle, Calendar } from 'lucide-react'
import { equipmentData } from '../data/equipment'
import { Badge, statusLabels } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { useCartStore } from '../store/cartStore'
import { EquipmentCard } from '../components/EquipmentCard'

function formatPrice(p: number) {
  return new Intl.NumberFormat('ru-RU').format(p)
}

function calcDays(start: string, end: string) {
  if (!start || !end) return 0
  const diff = (new Date(end).getTime() - new Date(start).getTime()) / (1000 * 60 * 60 * 24)
  return Math.max(1, Math.ceil(diff))
}

export const EquipmentDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { addItem, items } = useCartStore()

  const equipment = equipmentData.find((e) => e.id === id)

  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [added, setAdded] = useState(false)

  const isInCart = items.some((i) => i.equipment.id === id)
  const days = calcDays(startDate, endDate)

  const today = new Date().toISOString().split('T')[0]

  function totalPrice() {
    if (!equipment || !days) return 0
    if (days >= 30) {
      const m = Math.floor(days / 30)
      const r = days % 30
      return m * equipment.pricePerMonth + r * equipment.pricePerDay
    } else if (days >= 7) {
      const w = Math.floor(days / 7)
      const r = days % 7
      return w * equipment.pricePerWeek + r * equipment.pricePerDay
    }
    return days * equipment.pricePerDay
  }

  const handleAddToCart = () => {
    if (!equipment || !startDate || !endDate) return
    addItem(equipment, startDate, endDate)
    setAdded(true)
    setTimeout(() => setAdded(false), 2000)
  }

  useEffect(() => {
    if (equipment) {
      document.title = `${equipment.name} — ТЕХПРОКАТ`
    }
  }, [equipment])

  if (!equipment) {
    return (
      <div className="min-h-screen pt-16 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-400 text-lg mb-4">Техника не найдена</p>
          <Link to="/catalog">
            <Button>Вернуться в каталог</Button>
          </Link>
        </div>
      </div>
    )
  }

  const related = equipmentData
    .filter((e) => e.category === equipment.category && e.id !== equipment.id)
    .slice(0, 3)

  // Simple calendar showing booked dates
  const bookedDates = ['2024-03-25', '2024-03-26', '2024-03-27', '2024-04-01', '2024-04-02']

  return (
    <div className="min-h-screen pt-16">
      {/* Breadcrumb */}
      <div className="bg-gray-900/50 border-b border-gray-800/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Link to="/" className="hover:text-blue-400 transition-colors">Главная</Link>
            <ChevronRight size={14} />
            <Link to="/catalog" className="hover:text-blue-400 transition-colors">Каталог</Link>
            <ChevronRight size={14} />
            <Link to={`/catalog?category=${encodeURIComponent(equipment.category)}`} className="hover:text-blue-400 transition-colors">
              {equipment.category}
            </Link>
            <ChevronRight size={14} />
            <span className="text-gray-400">{equipment.name}</span>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid lg:grid-cols-2 gap-10">
          {/* Left — image + specs */}
          <div>
            <div className="relative rounded-xl overflow-hidden mb-6">
              <img
                src={equipment.image}
                alt={equipment.name}
                className="w-full h-80 object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-gray-950/60 via-transparent to-transparent" />
              <div className="absolute bottom-4 left-4 flex gap-2">
                <Badge variant={equipment.availability as 'available' | 'rented' | 'maintenance'}>
                  {statusLabels[equipment.availability]}
                </Badge>
                <span className="bg-blue-500/90 text-gray-900 text-xs font-bold px-2.5 py-1 rounded-md">
                  {equipment.category}
                </span>
              </div>
            </div>

            {/* Specs */}
            <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-6">
              <h2 className="font-bold text-gray-200 mb-4 text-lg">Технические характеристики</h2>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(equipment.specs).map(([key, value]) => (
                  <div key={key} className="bg-gray-800/60 rounded-lg p-3">
                    <div className="text-xs text-gray-500 mb-1">{key}</div>
                    <div className="text-sm font-semibold text-gray-200">{value}</div>
                  </div>
                ))}
              </div>

              <div className="mt-5 grid grid-cols-2 gap-3">
                <div className="bg-gray-800/60 rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-1">Масса</div>
                  <div className="text-sm font-semibold text-gray-200">{equipment.weight} т</div>
                </div>
                <div className="bg-gray-800/60 rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-1">Мощность</div>
                  <div className="text-sm font-semibold text-gray-200">{equipment.power}</div>
                </div>
              </div>
            </div>

            {/* Features */}
            <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-6 mt-5">
              <h2 className="font-bold text-gray-200 mb-4 text-lg">Особенности и комплектация</h2>
              <ul className="space-y-2.5">
                {equipment.features.map((f) => (
                  <li key={f} className="flex items-center gap-3 text-sm text-gray-400">
                    <CheckCircle size={16} className="text-blue-500 shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Right — info + booking */}
          <div>
            <h1 className="text-3xl font-black text-white mb-3">{equipment.name}</h1>

            <div className="flex items-center gap-4 mb-4">
              <div className="flex items-center gap-1">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Star
                    key={i}
                    size={14}
                    className={i < Math.floor(equipment.rating) ? 'text-blue-400 fill-blue-400' : 'text-gray-600'}
                  />
                ))}
                <span className="text-sm text-gray-400 ml-1">{equipment.rating.toFixed(1)}</span>
              </div>
              <span className="text-sm text-gray-600">{equipment.reviewCount} отзывов</span>
              <div className="flex items-center gap-1 text-sm text-gray-500">
                <MapPin size={12} />
                {equipment.location}
              </div>
            </div>

            <p className="text-gray-400 leading-relaxed mb-6">{equipment.description}</p>

            {/* Pricing cards */}
            <div className="grid grid-cols-3 gap-3 mb-6">
              {[
                { period: 'день', price: equipment.pricePerDay },
                { period: 'неделя', price: equipment.pricePerWeek },
                { period: 'месяц', price: equipment.pricePerMonth },
              ].map(({ period, price }) => (
                <div key={period} className="bg-gray-900 border border-gray-700/50 rounded-lg p-3 text-center hover:border-blue-500/30 transition-all">
                  <div className="text-xs text-gray-500 mb-1">{period}</div>
                  <div className="font-bold text-blue-400 text-sm">{formatPrice(price)} ₽</div>
                </div>
              ))}
            </div>

            {/* Booking form */}
            <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-5 mb-6">
              <h2 className="font-bold text-gray-200 mb-4 flex items-center gap-2">
                <Calendar size={18} className="text-blue-500" />
                Забронировать
              </h2>

              <div className="grid grid-cols-2 gap-3 mb-4">
                <div>
                  <label className="text-xs text-gray-500 mb-1.5 block">Дата начала</label>
                  <input
                    type="date"
                    value={startDate}
                    min={today}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 text-gray-100 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-blue-500 transition"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1.5 block">Дата окончания</label>
                  <input
                    type="date"
                    value={endDate}
                    min={startDate || today}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 text-gray-100 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-blue-500 transition"
                  />
                </div>
              </div>

              {days > 0 && (
                <div className="bg-gray-800 rounded-lg p-3 mb-4">
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-400">Период: {days} дней</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400 text-sm">Итого:</span>
                    <span className="text-xl font-bold text-blue-400">{formatPrice(totalPrice())} ₽</span>
                  </div>
                </div>
              )}

              <Button
                className="w-full gap-2"
                onClick={handleAddToCart}
                disabled={!startDate || !endDate || equipment.availability !== 'available' || isInCart}
              >
                <ShoppingCart size={16} />
                {isInCart ? 'Уже в корзине' : added ? 'Добавлено!' : 'Добавить в корзину'}
              </Button>

              {isInCart && (
                <button
                  onClick={() => navigate('/booking')}
                  className="w-full mt-2 py-2.5 text-sm font-medium text-blue-400 hover:text-blue-300 transition-colors cursor-pointer"
                >
                  Перейти к оформлению →
                </button>
              )}
            </div>

            {/* Calendar */}
            <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-5">
              <h3 className="font-bold text-gray-300 text-sm mb-3">Занятые даты (пример)</h3>
              <div className="grid grid-cols-7 gap-1 text-xs">
                {['Пн','Вт','Ср','Чт','Пт','Сб','Вс'].map((d) => (
                  <div key={d} className="text-center text-gray-600 py-1">{d}</div>
                ))}
                {Array.from({ length: 31 }).map((_, i) => {
                  const day = i + 1
                  const dateStr = `2024-03-${String(day).padStart(2, '0')}`
                  const isBooked = bookedDates.includes(dateStr)
                  return (
                    <div
                      key={i}
                      className={`text-center py-1.5 rounded text-xs ${
                        isBooked
                          ? 'bg-red-500/20 text-red-400'
                          : 'text-gray-500 hover:bg-gray-800'
                      }`}
                    >
                      {day}
                    </div>
                  )
                })}
              </div>
              <div className="flex gap-4 mt-3 text-xs text-gray-600">
                <span className="flex items-center gap-1"><span className="w-3 h-3 bg-red-500/20 rounded inline-block" /> Забронировано</span>
                <span className="flex items-center gap-1"><span className="w-3 h-3 bg-gray-800 rounded inline-block" /> Свободно</span>
              </div>
            </div>

            {/* Contact */}
            <div className="mt-4 flex items-center gap-3 p-4 bg-gray-900 border border-gray-700/50 rounded-xl">
              <Phone size={20} className="text-blue-500 shrink-0" />
              <div>
                <div className="text-sm text-gray-400">Вопросы по аренде</div>
                <a href="tel:+74951234567" className="font-bold text-white hover:text-blue-400 transition-colors">
                  +7 (495) 123-45-67
                </a>
              </div>
            </div>
          </div>
        </div>

        {/* Related */}
        {related.length > 0 && (
          <div className="mt-14">
            <h2 className="text-2xl font-black text-white mb-6">
              Похожая <span className="gradient-text">техника</span>
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {related.map((eq) => (
                <EquipmentCard key={eq.id} equipment={eq} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
