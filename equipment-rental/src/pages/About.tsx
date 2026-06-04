import React, { useEffect } from 'react'
import { PageTransition } from '../components/PageTransition'
import { Award, Users, Truck, Clock, CheckCircle } from 'lucide-react'

const team = [
  { name: 'Андрей Волков', role: 'Генеральный директор', exp: '20 лет в отрасли' },
  { name: 'Марина Соколова', role: 'Технический директор', exp: 'Инженер-механик, МГТУ' },
  { name: 'Дмитрий Петров', role: 'Руководитель парка', exp: 'Сертифицированный эксперт' },
  { name: 'Ольга Карпова', role: 'Менеджер по работе с клиентами', exp: '10 лет в строительстве' },
]

const certs = [
  'ISO 9001:2015 — Система менеджмента качества',
  'ГОСТ Р 12.0.006-2002 — Безопасность труда',
  'СТО НОСТРОЙ 2.13.81-2012 — Эксплуатация техники',
  'Лицензия Ростехнадзора № ВП-47-000234',
  'Сертификат Liebherr Authorized Dealer',
  'Авторизованный сервисный центр Caterpillar',
]

const fleetStats = [
  { icon: Truck, value: '500+', label: 'единиц техники' },
  { icon: Users, value: '1 200+', label: 'клиентов' },
  { icon: Award, value: '15', label: 'лет на рынке' },
  { icon: Clock, value: '24/7', label: 'техподдержка' },
]

export const About: React.FC = () => {
  useEffect(() => {
    document.title = 'О компании — ТЕХПРОКАТ'
  }, [])

  return (
    <PageTransition>
    <div className="min-h-screen pt-16">
      {/* Hero */}
      <div className="bg-gray-900/50 border-b border-gray-800/50 py-16">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 text-center">
          <h1 className="text-4xl sm:text-5xl font-black text-white mb-4">
            О компании <span className="gradient-text">ТЕХПРОКАТ</span>
          </h1>
          <p className="text-gray-400 text-lg leading-relaxed">
            С 2009 года мы обеспечиваем строительные, дорожные и инфраструктурные проекты России профессиональной спецтехникой. Наш парк — более 500 единиц, команда — более 200 специалистов.
          </p>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-16">
          {fleetStats.map(({ icon: Icon, value, label }) => (
            <div key={label} className="bg-gray-900 border border-gray-700/50 rounded-xl p-5 text-center">
              <Icon size={28} className="text-blue-500 mx-auto mb-3" />
              <div className="text-3xl font-black text-white mb-1">{value}</div>
              <div className="text-sm text-gray-500">{label}</div>
            </div>
          ))}
        </div>

        {/* Story */}
        <div className="grid md:grid-cols-2 gap-12 mb-16 items-center">
          <div>
            <h2 className="text-2xl font-black text-white mb-4">Наша история</h2>
            <div className="space-y-4 text-gray-400 text-sm leading-relaxed">
              <p>
                ТЕХПРОКАТ основан в 2009 году группой инженеров и строителей, столкнувшихся с проблемой — найти качественную спецтехнику в аренду в нужные сроки и без лишней бюрократии было крайне сложно.
              </p>
              <p>
                Начав с трёх экскаваторов и небольшого офиса в Подмосковье, компания выросла в одного из крупнейших операторов аренды спецтехники в Московском регионе. Сегодня наш парк насчитывает более 500 единиц техники ведущих мировых производителей.
              </p>
              <p>
                Мы работаем с крупнейшими строительными группами России, государственными структурами, муниципальными предприятиями и частными застройщиками. Наши клиенты — это не просто заказчики: мы выстраиваем долгосрочное партнёрство.
              </p>
            </div>
          </div>
          <div className="space-y-4">
            {[
              { year: '2009', event: 'Основание компании, первые 3 экскаватора' },
              { year: '2012', event: 'Расширение парка до 50 единиц, открытие 2 складов' },
              { year: '2015', event: 'Запуск онлайн-системы заказов, 200 единиц техники' },
              { year: '2018', event: 'Авторизация Liebherr и Caterpillar, 350 единиц' },
              { year: '2022', event: 'Запуск системы ИИ-подбора, парк 500+ единиц' },
            ].map(({ year, event }) => (
              <div key={year} className="flex gap-4">
                <div className="w-12 shrink-0 text-right">
                  <span className="text-blue-400 font-bold text-sm">{year}</span>
                </div>
                <div className="flex gap-3 items-start">
                  <div className="w-2 h-2 rounded-full bg-blue-500 mt-1.5 shrink-0" />
                  <span className="text-gray-400 text-sm">{event}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Team */}
        <div className="mb-16">
          <h2 className="text-2xl font-black text-white mb-6 text-center">
            Команда <span className="gradient-text">руководства</span>
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
            {team.map((member) => (
              <div key={member.name} className="bg-gray-900 border border-gray-700/50 rounded-xl p-5 text-center hover:border-blue-500/30 transition-all">
                <div className="w-16 h-16 bg-gradient-to-br from-blue-500/20 to-blue-600/10 border border-blue-500/20 rounded-full flex items-center justify-center mx-auto mb-3">
                  <Users size={24} className="text-blue-400" />
                </div>
                <h3 className="font-bold text-gray-200 text-sm mb-1">{member.name}</h3>
                <div className="text-xs text-blue-400 mb-1">{member.role}</div>
                <div className="text-xs text-gray-600">{member.exp}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Certifications */}
        <div className="mb-16">
          <h2 className="text-2xl font-black text-white mb-6 text-center">
            Лицензии и <span className="gradient-text">сертификаты</span>
          </h2>
          <div className="grid md:grid-cols-2 gap-3">
            {certs.map((cert) => (
              <div key={cert} className="flex items-center gap-3 bg-gray-900 border border-gray-700/50 rounded-lg p-3">
                <CheckCircle size={16} className="text-blue-500 shrink-0" />
                <span className="text-sm text-gray-400">{cert}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Partners */}
        <div>
          <h2 className="text-2xl font-black text-white mb-6 text-center">Партнёры и бренды</h2>
          <div className="grid grid-cols-3 md:grid-cols-6 gap-4">
            {['Liebherr', 'Caterpillar', 'Komatsu', 'Volvo CE', 'Bomag', 'Wirtgen', 'JCB', 'Bauer', 'Potain', 'Grove', 'Dynapac', 'Atlas Copco'].map((brand) => (
              <div
                key={brand}
                className="bg-gray-900 border border-gray-700/50 rounded-lg p-3 text-center hover:border-blue-500/30 transition-all"
              >
                <div className="text-xs font-bold text-gray-500">{brand}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
    </PageTransition>
  )
}
