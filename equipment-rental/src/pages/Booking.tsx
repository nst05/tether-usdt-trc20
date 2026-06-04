import React, { useEffect, useState } from 'react'
import { PageTransition } from '../components/PageTransition'
import { Link } from 'react-router-dom'
import { ShoppingCart, Trash2, Check, ChevronRight, ChevronLeft } from 'lucide-react'
import { useCartStore } from '../store/cartStore'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'

function formatPrice(p: number) {
  return new Intl.NumberFormat('ru-RU').format(p)
}

interface FormData {
  name: string
  email: string
  phone: string
  company: string
  address: string
  notes: string
}

const EMPTY_FORM: FormData = { name: '', email: '', phone: '', company: '', address: '', notes: '' }

function generateOrderId() {
  return `ORD-${new Date().getFullYear()}-${String(Math.floor(Math.random() * 9000 + 1000))}`
}

export const Booking: React.FC = () => {
  const { items, removeItem, clearCart, getTotalPrice } = useCartStore()

  const [step, setStep] = useState(1)
  const [form, setForm] = useState<FormData>(EMPTY_FORM)
  const [errors, setErrors] = useState<Partial<FormData>>({})
  const [orderId] = useState(generateOrderId)

  useEffect(() => {
    document.title = 'Оформление заявки — ТЕХПРОКАТ'
  }, [])

  const validate = (): boolean => {
    const e: Partial<FormData> = {}
    if (!form.name.trim()) e.name = 'Введите ваше имя'
    if (!form.email.trim() || !form.email.includes('@')) e.email = 'Введите корректный email'
    if (!form.phone.trim() || form.phone.length < 10) e.phone = 'Введите номер телефона'
    if (step === 2 && !form.address.trim()) e.address = 'Укажите адрес объекта'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const handleNext = () => {
    if (validate()) setStep((s) => s + 1)
  }

  const handleConfirm = () => {
    if (validate()) {
      setStep(4)
      setTimeout(() => clearCart(), 500)
    }
  }

  if (items.length === 0 && step < 4) {
    return (
      <div className="min-h-screen pt-16 flex items-center justify-center">
        <div className="text-center">
          <ShoppingCart size={48} className="text-gray-700 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-gray-400 mb-2">Корзина пуста</h2>
          <p className="text-gray-600 mb-6">Добавьте технику из каталога</p>
          <Link to="/catalog">
            <Button>Перейти в каталог</Button>
          </Link>
        </div>
      </div>
    )
  }

  return (
    <PageTransition>
    <div className="min-h-screen pt-16">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-3xl font-black text-white mb-2">
          Оформление <span className="gradient-text">заявки</span>
        </h1>

        {step < 4 && (
          <div className="flex items-center gap-2 mb-8">
            {[1, 2, 3].map((s) => (
              <React.Fragment key={s}>
                <div className={`flex items-center gap-2 ${s <= step ? 'text-blue-400' : 'text-gray-600'}`}>
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border ${
                    s < step ? 'bg-blue-500 border-blue-500 text-gray-900' :
                    s === step ? 'border-blue-500 text-blue-400' :
                    'border-gray-700 text-gray-600'
                  }`}>
                    {s < step ? <Check size={12} /> : s}
                  </div>
                  <span className="text-sm hidden sm:block">
                    {s === 1 ? 'Контакты' : s === 2 ? 'Доставка' : 'Подтверждение'}
                  </span>
                </div>
                {s < 3 && <div className={`flex-1 h-px ${s < step ? 'bg-blue-500' : 'bg-gray-700'}`} />}
              </React.Fragment>
            ))}
          </div>
        )}

        {step < 4 && (
          <div className="grid lg:grid-cols-3 gap-8">
            {/* Form */}
            <div className="lg:col-span-2">
              {step === 1 && (
                <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-6 space-y-4">
                  <h2 className="font-bold text-gray-200 text-lg mb-2">Контактная информация</h2>
                  <Input
                    label="ФИО *"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    error={errors.name}
                    placeholder="Иванов Иван Иванович"
                  />
                  <div className="grid grid-cols-2 gap-4">
                    <Input
                      label="Email *"
                      type="email"
                      value={form.email}
                      onChange={(e) => setForm({ ...form, email: e.target.value })}
                      error={errors.email}
                      placeholder="mail@company.ru"
                    />
                    <Input
                      label="Телефон *"
                      type="tel"
                      value={form.phone}
                      onChange={(e) => setForm({ ...form, phone: e.target.value })}
                      error={errors.phone}
                      placeholder="+7 (___) ___-__-__"
                    />
                  </div>
                  <Input
                    label="Компания (необязательно)"
                    value={form.company}
                    onChange={(e) => setForm({ ...form, company: e.target.value })}
                    placeholder="ООО «МояКомпания»"
                  />
                  <div className="flex justify-end mt-4">
                    <Button onClick={handleNext} className="gap-2">
                      Далее <ChevronRight size={16} />
                    </Button>
                  </div>
                </div>
              )}

              {step === 2 && (
                <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-6 space-y-4">
                  <h2 className="font-bold text-gray-200 text-lg mb-2">Данные доставки</h2>
                  <Input
                    label="Адрес объекта *"
                    value={form.address}
                    onChange={(e) => setForm({ ...form, address: e.target.value })}
                    error={errors.address}
                    placeholder="Москва, ул. Строительная, 1"
                  />
                  <div>
                    <label className="text-sm font-medium text-gray-300 mb-1.5 block">Примечания к заявке</label>
                    <textarea
                      value={form.notes}
                      onChange={(e) => setForm({ ...form, notes: e.target.value })}
                      rows={4}
                      placeholder="Дополнительные пожелания, особенности объекта..."
                      className="w-full bg-gray-800 border border-gray-700 text-gray-100 rounded-lg px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-600/20 transition placeholder:text-gray-600 resize-none"
                    />
                  </div>
                  <div className="flex justify-between mt-4">
                    <Button variant="ghost" onClick={() => setStep(1)} className="gap-2">
                      <ChevronLeft size={16} /> Назад
                    </Button>
                    <Button onClick={handleNext} className="gap-2">
                      Далее <ChevronRight size={16} />
                    </Button>
                  </div>
                </div>
              )}

              {step === 3 && (
                <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-6">
                  <h2 className="font-bold text-gray-200 text-lg mb-5">Подтверждение заявки</h2>
                  <div className="space-y-3 mb-5">
                    {[
                      { label: 'ФИО', value: form.name },
                      { label: 'Email', value: form.email },
                      { label: 'Телефон', value: form.phone },
                      form.company && { label: 'Компания', value: form.company },
                      { label: 'Адрес объекта', value: form.address },
                      form.notes && { label: 'Примечания', value: form.notes },
                    ].filter(Boolean).map((item) => {
                      const i = item as { label: string; value: string }
                      return (
                        <div key={i.label} className="flex gap-3">
                          <span className="text-gray-500 text-sm w-32 shrink-0">{i.label}:</span>
                          <span className="text-gray-300 text-sm">{i.value}</span>
                        </div>
                      )
                    })}
                  </div>
                  <div className="flex justify-between mt-6">
                    <Button variant="ghost" onClick={() => setStep(2)} className="gap-2">
                      <ChevronLeft size={16} /> Назад
                    </Button>
                    <Button onClick={handleConfirm} className="gap-2">
                      <Check size={16} />
                      Подтвердить заявку
                    </Button>
                  </div>
                </div>
              )}
            </div>

            {/* Cart sidebar */}
            <div>
              <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-5 sticky top-20">
                <h2 className="font-bold text-gray-200 mb-4">Корзина</h2>
                <div className="space-y-4 mb-4">
                  {items.map((item) => (
                    <div key={item.equipment.id} className="flex gap-3">
                      <img
                        src={item.equipment.image}
                        alt={item.equipment.name}
                        className="w-16 h-12 object-cover rounded-lg"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-gray-300 truncate">{item.equipment.name}</div>
                        <div className="text-xs text-gray-600">{item.days} дней</div>
                        <div className="text-sm font-bold text-blue-400">{formatPrice(item.totalPrice)} ₽</div>
                      </div>
                      <button
                        onClick={() => removeItem(item.equipment.id)}
                        className="text-gray-600 hover:text-red-400 transition-colors p-1 cursor-pointer"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
                <div className="border-t border-gray-800 pt-4">
                  <div className="flex justify-between text-sm text-gray-400 mb-1">
                    <span>Позиций:</span>
                    <span>{items.length}</span>
                  </div>
                  <div className="flex justify-between font-bold">
                    <span className="text-gray-300">Итого:</span>
                    <span className="text-blue-400 text-lg">{formatPrice(getTotalPrice())} ₽</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Success state */}
        {step === 4 && (
          <div className="text-center py-20 animate-fade-in">
            <div className="w-20 h-20 bg-emerald-500/20 border border-emerald-500/40 rounded-full flex items-center justify-center mx-auto mb-6">
              <Check size={36} className="text-emerald-400" />
            </div>
            <h2 className="text-3xl font-black text-white mb-3">Заявка отправлена!</h2>
            <p className="text-gray-400 mb-2">Ваш номер заявки:</p>
            <div className="inline-block bg-gray-900 border border-blue-500/30 rounded-xl px-6 py-3 mb-6">
              <span className="text-2xl font-mono font-bold text-blue-400">{orderId}</span>
            </div>
            <p className="text-gray-500 max-w-md mx-auto mb-8">
              Наш менеджер свяжется с вами в течение 30 минут для подтверждения заявки и уточнения деталей доставки.
            </p>
            <div className="flex gap-4 justify-center">
              <Link to="/catalog">
                <Button variant="secondary">Продолжить просмотр</Button>
              </Link>
              <Link to="/">
                <Button>На главную</Button>
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
    </PageTransition>
  )
}
