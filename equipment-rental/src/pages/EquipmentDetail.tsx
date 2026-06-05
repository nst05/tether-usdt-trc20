import React, { useEffect, useState } from 'react'
import { PageTransition } from '../components/PageTransition'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Star, MapPin, ChevronRight, ShoppingCart, Phone, CheckCircle, Calendar, Bell, Calculator } from 'lucide-react'
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

interface PriceBreakdown {
  total: number
  label: string
}

function calcPriceBreakdown(
  days: number,
  pricePerDay: number,
  pricePerWeek: number,
  pricePerMonth: number
): PriceBreakdown {
  if (days >= 30) {
    const months = Math.floor(days / 30)
    const remaining = days % 30
    const total = months * pricePerMonth + remaining * pricePerDay
    const label = remaining > 0
      ? `${months} мес × ${formatPrice(pricePerMonth)} ₽ + ${remaining} дн × ${formatPrice(pricePerDay)} ₽ = ${formatPrice(total)} ₽ (применена месячная ставка)`
      : `${months} мес × ${formatPrice(pricePerMonth)} ₽ = ${formatPrice(total)} ₽ (применена месячная ставка)`
    return { total, label }
  } else if (days >= 7) {
    const weeks = Math.floor(days / 7)
    const remaining = days % 7
    const total = weeks * pricePerWeek + remaining * pricePerDay
    const label = remaining > 0
      ? `${weeks} нед × ${formatPrice(pricePerWeek)} ₽ + ${remaining} дн × ${formatPrice(pricePerDay)} ₽ = ${formatPrice(total)} ₽ (применена недельная ставка)`
      : `${weeks} нед × ${formatPrice(pricePerWeek)} ₽ = ${formatPrice(total)} ₽ (применена недельная ставка)`
    return { total, label }
  }
  const total = days * pricePerDay
  return {
    total,
    label: `${days} дн × ${formatPrice(pricePerDay)} ₽ = ${formatPrice(total)} ₽`,
  }
}

export const EquipmentDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { addItem, items } = useCartStore()

  const equipment = equipmentData.find((e) => e.id === id)

  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [added, setAdded] = useState(false)

  // Availability notification state
  const [notifyEmail, setNotifyEmail] = useState('')
  const [notifySent, setNotifySent] = useState(false)

  // Rental calculator state
  const [calcStart, setCalcStart] = useState('')
  const [calcEnd, setCalcEnd] = useState('')

  const isInCart = items.some((i) => i.equipment.id === id)
  const days = calcDays(startDate, endDate)
  const calcDaysCount = calcDays(calcStart, calcEnd)

  const today = new Date().toISOString().split('T')[0]

  function totalPrice() {
    if (!equipment || !days) return 0
    return calcPriceBreakdown(days, equipment.pricePerDay, equipment.pricePerWeek, equipment.pricePerMonth).total
  }

  const handleAddToCart = () => {
    if (!equipment || !startDate || !endDate) return
    addItem(equipment, startDate, endDate)
    setAdded(true)
    setTimeout(() => setAdded(false), 2000)
  }

  const handleCalcBook = () => {
    if (!equipment || !calcStart || !calcEnd) return
    addItem(equipment, calcStart, calcEnd)
    setAdded(true)
    setTimeout(() => setAdded(false), 2000)
    navigate('/booking')
  }

  const handleNotifySubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!notifyEmail.trim()) return
    setNotifySent(true)
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

  const bookedDates = ['2024-03-25', '2024-03-26', '2024-03-27', '2024-04-01', '2024-04-02']

  const calcBreakdown = calcDaysCount > 0 && equipment
    ? calcPriceBreakdown(calcDaysCount, equipment.pricePerDay, equipment.pricePerWeek, equipment.pricePerMonth)
    : null

  return (
    <PageTransition>
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
                <span className="bg-amber-500/90 text-black text-xs font-bold px-2.5 py-1 rounded-md">
                  {equipment.category}
                </span>
              </div>
            </div>

            {/* Specs */}
            <div className="bg-[#111111] border border-white/8 rounded-xl p-6">
              <h2 className="font-bold text-gray-200 mb-4 text-lg">Технические характеристики</h2>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(equipment.specs).map(([key, value]) => (
                  <div key={key} className="bg-[#1A1A1A] rounded-lg p-3">
                    <div className="text-xs text-gray-500 mb-1">{key}</div>
                    <div className="text-sm font-semibold text-gray-200">{value}</div>
                  </div>
                ))}
              </div>

              <div className="mt-5 grid grid-cols-2 gap-3">
                <div className="bg-[#1A1A1A] rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-1">Масса</div>
                  <div className="text-sm font-semibold text-gray-200">{equipment.weight} т</div>
                </div>
                <div className="bg-[#1A1A1A] rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-1">Мощность</div>
                  <div className="text-sm font-semibold text-gray-200">{equipment.power}</div>
                </div>
              </div>
            </div>

            {/* Features */}
            <div className="bg-[#111111] border border-white/8 rounded-xl p-6 mt-5">
              <h2 className="font-bold text-gray-200 mb-4 text-lg">Особенности и комплектация</h2>
              <ul className="space-y-2.5">
                {equipment.features.map((f) => (
                  <li key={f} className="flex items-center gap-3 text-sm text-gray-400">
                    <CheckCircle size={16} className="text-amber-500 shrink-0" />
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
                    className={i < Math.floor(equipment.rating) ? 'text-amber-400 fill-amber-400' : 'text-gray-600'}
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
                <div key={period} className="bg-[#111111] border border-white/8 rounded-lg p-3 text-center hover:border-amber-500/30 transition-all">
                  <div className="text-xs text-gray-500 mb-1">{period}</div>
                  <div className="font-bold text-amber-400 text-sm">{formatPrice(price)} ₽</div>
                </div>
              ))}
            </div>

            {/* Booking form */}
            <div className="bg-[#111111] border border-white/8 rounded-xl p-5 mb-5">
              <h2 className="font-bold text-gray-200 mb-4 flex items-center gap-2">
                <Calendar size={18} className="text-amber-500" />
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
                    className="w-full bg-[#1A1A1A] border border-white/8 text-gray-100 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-amber-500/50 transition"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1.5 block">Дата окончания</label>
                  <input
                    type="date"
                    value={endDate}
                    min={startDate || today}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full bg-[#1A1A1A] border border-white/8 text-gray-100 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-amber-500/50 transition"
                  />
                </div>
              </div>

              {days > 0 && (
                <div className="bg-[#1A1A1A] rounded-lg p-3 mb-4">
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-400">Период: {days} дней</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400 text-sm">Итого:</span>
                    <span className="text-xl font-bold text-amber-400">{formatPrice(totalPrice())} ₽</span>
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
                  className="w-full mt-2 py-2.5 text-sm font-medium text-amber-400 hover:text-amber-300 transition-colors cursor-pointer"
                >
                  Перейти к оформлению →
                </button>
              )}
            </div>

            {/* Availability Notification */}
            {equipment.availability !== 'available' && (
              <div className="bg-[#111111] border border-amber-500/20 rounded-xl p-5 mb-5">
                <h3 className="font-bold text-gray-200 mb-3 flex items-center gap-2">
                  <Bell size={16} className="text-amber-400" />
                  Уведомить о появлении
                </h3>
                {notifySent ? (
                  <div className="flex items-center gap-2 text-emerald-400 text-sm">
                    <CheckCircle size={16} />
                    Вы будете уведомлены когда техника станет доступна
                  </div>
                ) : (
                  <form onSubmit={handleNotifySubmit} className="flex gap-2">
                    <input
                      type="email"
                      value={notifyEmail}
                      onChange={(e) => setNotifyEmail(e.target.value)}
                      placeholder="Ваш email"
                      required
                      className="flex-1 bg-[#1A1A1A] border border-white/8 text-gray-100 rounded-lg px-3 py-2 text-sm outline-none focus:border-amber-500/50 transition placeholder:text-gray-600"
                    />
                    <Button type="submit" size="sm" className="gap-1.5 shrink-0">
                      <Bell size={14} />
                      Уведомить
                    </Button>
                  </form>
                )}
              </div>
            )}

            {/* Rental Calculator */}
            <div className="bg-[#111111] border border-white/8 rounded-xl p-5 mb-5">
              <h2 className="font-bold text-gray-200 mb-4 flex items-center gap-2">
                <Calculator size={18} className="text-amber-500" />
                Рассчитать стоимость
              </h2>

              <div className="grid grid-cols-2 gap-3 mb-4">
                <div>
                  <label className="text-xs text-gray-500 mb-1.5 block">Дата начала</label>
                  <input
                    type="date"
                    value={calcStart}
                    min={today}
                    onChange={(e) => setCalcStart(e.target.value)}
                    className="w-full bg-[#1A1A1A] border border-white/8 text-gray-100 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-amber-500/50 transition"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1.5 block">Дата окончания</label>
                  <input
                    type="date"
                    value={calcEnd}
                    min={calcStart || today}
                    onChange={(e) => setCalcEnd(e.target.value)}
                    className="w-full bg-[#1A1A1A] border border-white/8 text-gray-100 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-amber-500/50 transition"
                  />
                </div>
              </div>

              {calcBreakdown && calcDaysCount > 0 && (
                <div className="bg-[#1A1A1A] border border-amber-500/15 rounded-lg p-4 mb-4">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs text-gray-500 uppercase tracking-wider">Расчёт</span>
                    <span className="text-xs text-gray-600">{calcDaysCount} дн.</span>
                  </div>
                  <p className="text-xs text-gray-400 mb-3 leading-relaxed">{calcBreakdown.label}</p>
                  <div className="flex justify-between items-end">
                    <span className="text-sm text-gray-400">Итого:</span>
                    <span className="text-2xl font-black text-amber-400">
                      {formatPrice(calcBreakdown.total)} ₽
                    </span>
                  </div>
                </div>
              )}

              <Button
                className="w-full gap-2"
                onClick={handleCalcBook}
                disabled={!calcStart || !calcEnd || equipment.availability !== 'available'}
              >
                <ShoppingCart size={16} />
                Забронировать
              </Button>
            </div>

            {/* Calendar */}
            <div className="bg-[#111111] border border-white/8 rounded-xl p-5">
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
                          : 'text-gray-500 hover:bg-[#1A1A1A]'
                      }`}
                    >
                      {day}
                    </div>
                  )
                })}
              </div>
              <div className="flex gap-4 mt-3 text-xs text-gray-600">
                <span className="flex items-center gap-1"><span className="w-3 h-3 bg-red-500/20 rounded inline-block" /> Забронировано</span>
                <span className="flex items-center gap-1"><span className="w-3 h-3 bg-[#1A1A1A] rounded inline-block" /> Свободно</span>
              </div>
            </div>

            {/* Contact */}
            <div className="mt-4 flex items-center gap-3 p-4 bg-[#111111] border border-white/8 rounded-xl">
              <Phone size={20} className="text-amber-500 shrink-0" />
              <div>
                <div className="text-sm text-gray-400">Вопросы по аренде</div>
                <a href="tel:+74951234567" className="font-bold text-white hover:text-amber-400 transition-colors">
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
              Похожая <span className="text-amber-400">техника</span>
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
    </PageTransition>
  )
}
