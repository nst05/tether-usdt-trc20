import React, { useEffect, useState } from 'react'
import { PageTransition } from '../components/PageTransition'
import { Phone, Mail, MapPin, Clock, Send, Check } from 'lucide-react'
import { Input } from '../components/ui/Input'
import { Button } from '../components/ui/Button'

const contacts = [
  {
    icon: Phone,
    label: 'Телефон',
    values: ['+7 (495) 123-45-67', '8-800-555-35-35 (бесплатно)'],
  },
  {
    icon: Mail,
    label: 'Email',
    values: ['info@tehprokat.ru', 'sales@tehprokat.ru'],
  },
  {
    icon: MapPin,
    label: 'Адрес офиса',
    values: ['125040, Москва', 'ул. Промышленная, 12, стр. 3'],
  },
  {
    icon: Clock,
    label: 'Режим работы',
    values: ['Пн–Пт: 8:00 – 19:00', 'Сб: 9:00 – 16:00, Вс: выходной'],
  },
]

const warehouses = [
  { name: 'Склад №1 (Москва Север)', address: 'Москва, Дмитровское ш., 79', tel: '+7 (495) 123-45-68' },
  { name: 'Склад №2 (Москва Юг)', address: 'Москва, Каширское ш., 22', tel: '+7 (495) 123-45-69' },
  { name: 'Склад №3 (Подольск)', address: 'Подольск, ул. Заводская, 15', tel: '+7 (495) 123-45-70' },
  { name: 'Склад №4 (Химки)', address: 'Химки, Ленинградское ш., 18', tel: '+7 (495) 123-45-71' },
]

export const Contact: React.FC = () => {
  useEffect(() => {
    document.title = 'Контакты — ТЕХПРОКАТ'
  }, [])

  const [form, setForm] = useState({ name: '', email: '', phone: '', message: '' })
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setTimeout(() => {
      setLoading(false)
      setSubmitted(true)
    }, 1200)
  }

  return (
    <PageTransition>
    <div className="min-h-screen pt-16">
      {/* Hero */}
      <div className="bg-gray-900/50 border-b border-gray-800/50 py-12">
        <div className="max-w-4xl mx-auto px-4 text-center">
          <h1 className="text-4xl font-black text-white mb-3">
            <span className="gradient-text">Контакты</span>
          </h1>
          <p className="text-gray-500">Свяжитесь с нами любым удобным способом</p>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid lg:grid-cols-2 gap-12">
          {/* Left */}
          <div>
            {/* Contact info cards */}
            <div className="grid grid-cols-2 gap-4 mb-8">
              {contacts.map(({ icon: Icon, label, values }) => (
                <div key={label} className="bg-gray-900 border border-gray-700/50 rounded-xl p-4 hover:border-blue-500/30 transition-all">
                  <Icon size={20} className="text-blue-500 mb-3" />
                  <div className="text-xs text-gray-500 mb-1 uppercase tracking-wider">{label}</div>
                  {values.map((v) => (
                    <div key={v} className="text-sm text-gray-300">{v}</div>
                  ))}
                </div>
              ))}
            </div>

            {/* Fake map */}
            <div className="bg-gray-900 border border-gray-700/50 rounded-xl overflow-hidden mb-8" style={{ height: 240 }}>
              <div className="relative w-full h-full bg-grid bg-gray-950">
                {/* Fake map grid overlay */}
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="text-center">
                    <div className="w-10 h-10 bg-amber-500 rounded-full flex items-center justify-center mx-auto mb-2 shadow-[0_0_20px_rgba(245,158,11,0.6)]">
                      <MapPin size={18} className="text-gray-900" />
                    </div>
                    <div className="text-xs text-gray-400 bg-gray-900/80 px-3 py-1.5 rounded-lg">
                      Москва, ул. Промышленная, 12
                    </div>
                  </div>
                </div>
                {/* Grid lines */}
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={`h${i}`} className="absolute w-full border-t border-blue-500/5" style={{ top: `${(i + 1) * 16.67}%` }} />
                ))}
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={`v${i}`} className="absolute h-full border-l border-blue-500/5" style={{ left: `${(i + 1) * 12.5}%` }} />
                ))}
              </div>
            </div>

            {/* Warehouses */}
            <h3 className="font-bold text-gray-200 mb-4">Склады техники</h3>
            <div className="grid grid-cols-2 gap-3">
              {warehouses.map((w) => (
                <div key={w.name} className="bg-gray-900 border border-gray-700/50 rounded-lg p-3">
                  <div className="text-xs font-bold text-blue-400 mb-1">{w.name}</div>
                  <div className="text-xs text-gray-500">{w.address}</div>
                  <div className="text-xs text-gray-400 mt-1">{w.tel}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Right — contact form */}
          <div>
            <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-6">
              <h2 className="font-bold text-gray-200 text-lg mb-5">Написать нам</h2>

              {submitted ? (
                <div className="text-center py-12">
                  <div className="w-16 h-16 bg-emerald-500/20 border border-emerald-500/40 rounded-full flex items-center justify-center mx-auto mb-4">
                    <Check size={28} className="text-emerald-400" />
                  </div>
                  <h3 className="text-lg font-bold text-white mb-2">Сообщение отправлено!</h3>
                  <p className="text-gray-500 text-sm">Мы ответим вам в течение рабочего дня.</p>
                  <button
                    onClick={() => { setSubmitted(false); setForm({ name: '', email: '', phone: '', message: '' }) }}
                    className="mt-6 text-blue-400 text-sm hover:underline cursor-pointer"
                  >
                    Отправить ещё одно сообщение
                  </button>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-4">
                  <Input
                    label="Ваше имя *"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="Иван Иванов"
                    required
                  />
                  <div className="grid grid-cols-2 gap-4">
                    <Input
                      label="Email *"
                      type="email"
                      value={form.email}
                      onChange={(e) => setForm({ ...form, email: e.target.value })}
                      placeholder="mail@company.ru"
                      required
                    />
                    <Input
                      label="Телефон"
                      type="tel"
                      value={form.phone}
                      onChange={(e) => setForm({ ...form, phone: e.target.value })}
                      placeholder="+7 (___) ___-__-__"
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium text-gray-300 mb-1.5 block">Сообщение *</label>
                    <textarea
                      value={form.message}
                      onChange={(e) => setForm({ ...form, message: e.target.value })}
                      rows={5}
                      placeholder="Опишите ваш запрос..."
                      required
                      className="w-full bg-gray-800 border border-gray-700 text-gray-100 rounded-lg px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-600/20 transition placeholder:text-gray-600 resize-none"
                    />
                  </div>
                  <Button type="submit" loading={loading} className="w-full gap-2">
                    <Send size={16} />
                    Отправить сообщение
                  </Button>
                  <p className="text-xs text-gray-600 text-center">
                    Нажимая кнопку, вы соглашаетесь с политикой обработки персональных данных
                  </p>
                </form>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
    </PageTransition>
  )
}
