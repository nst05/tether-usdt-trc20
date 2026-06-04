import React, { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ChevronRight, Zap, Shield, Phone, Star, ArrowRight, Wrench, Truck, CheckCircle, Award, Clock } from 'lucide-react'
import { Button } from '../components/ui/Button'
import { EquipmentCard } from '../components/EquipmentCard'
import { PageTransition } from '../components/PageTransition'
import { equipmentData } from '../data/equipment'

const stats = [
  { value: '500+', label: 'единиц техники', icon: Truck },
  { value: '1 200+', label: 'завершённых проектов', icon: CheckCircle },
  { value: '15', label: 'лет на рынке', icon: Award },
  { value: '24/7', label: 'поддержка', icon: Clock },
]

const steps = [
  {
    num: '01',
    title: 'Выберите технику',
    desc: 'Воспользуйтесь каталогом или запустите Мастер подбора — система подберёт оптимальный пакет за 30 секунд.' },
  {
    num: '02',
    title: 'Оформите заявку',
    desc: 'Укажите даты аренды, адрес объекта и контактные данные. Подтверждение придёт в течение 30 минут.' },
  {
    num: '03',
    title: 'Получите технику',
    desc: 'Доставим технику на объект в согласованные сроки. Профессиональный оператор при необходимости — в комплекте.' },
]

const categoryList = [
  {
    name: 'Экскаваторы', count: 5,
    img: 'https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=600&auto=format&fit=crop&q=80' },
  {
    name: 'Краны', count: 3,
    img: 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600&auto=format&fit=crop&q=80' },
  {
    name: 'Бульдозеры', count: 2,
    img: 'https://images.unsplash.com/photo-1526040652367-ac003a0475fe?w=600&auto=format&fit=crop&q=80' },
  {
    name: 'Погрузчики', count: 4,
    img: 'https://images.unsplash.com/photo-1590496793929-36417d3117de?w=600&auto=format&fit=crop&q=80' },
  {
    name: 'Дорожная техника', count: 5,
    img: 'https://images.unsplash.com/photo-1581094794329-c8112a89af12?w=600&auto=format&fit=crop&q=80' },
  {
    name: 'Буровая техника', count: 3,
    img: 'https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=600&auto=format&fit=crop&q=80' },
]

const testimonials = [
  {
    name: 'Игорь Смирнов', company: 'ГК «ПромСтрой»',
    text: 'Арендовали экскаватор CAT 320 на месяц. Техника пришла в идеальном состоянии, оператор — профессионал высокого класса. Все документы оформлены быстро и без лишних вопросов.',
    rating: 5 },
  {
    name: 'Анна Белякова', company: 'ООО «ДорСервис»',
    text: 'Пользуемся Мастером подбора регулярно — это реально экономит время. Система точно подобрала пакет для дорожного проекта, сэкономили 18% по сравнению с раздельной арендой.',
    rating: 5 },
  {
    name: 'Павел Орлов', company: 'АО «СтройИнвест»',
    text: 'Арендовали башенный кран на 2 месяца для ЖК. Монтаж, обслуживание, демонтаж — всё включено в стоимость. Никаких скрытых платежей. Рекомендую.',
    rating: 5 },
]

const advantages = [
  { title: 'Собственный парк', desc: 'Вся техника в нашей собственности — никаких посредников и наценок' },
  { title: 'Техобслуживание', desc: 'Каждая единица проходит ТО перед выездом на объект' },
  { title: 'Опытные операторы', desc: 'Штат из 80+ сертифицированных операторов с опытом от 5 лет' },
  { title: 'Договор и документы', desc: 'Полный пакет документов для бухгалтерии, работаем по НДС' },
]

/* reusable animation helper */
const inView = {
  hidden: { opacity: 0, y: 32 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5} },
}

export const Home: React.FC = () => {
  useEffect(() => {
    document.title = 'ТЕХПРОКАТ — Аренда спецтехники'
  }, [])

  const featured = equipmentData.slice(0, 6)

  return (
    <PageTransition>
      <div className="min-h-screen">

        {/* ─── HERO ─── */}
        <section className="relative min-h-screen flex items-center overflow-hidden">
          <div
            className="absolute inset-0 bg-cover bg-center bg-no-repeat"
            style={{ backgroundImage: 'url(https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=1920&auto=format&fit=crop&q=80)' }}
          />
          <div className="absolute inset-0 bg-black/72" />
          <div className="absolute inset-0 bg-gradient-to-r from-black/60 via-black/30 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-black/20" />
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-amber-500/80 to-transparent" />

          <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 pb-20">
            <div className="max-w-2xl">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1, duration: 0.5 }}
                className="inline-flex items-center gap-2 bg-amber-500/10 border border-amber-500/30 rounded-sm px-4 py-1.5 mb-8"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                <span className="text-xs text-amber-300 font-semibold uppercase tracking-[0.15em]">
                  Более 500 единиц техники в наличии
                </span>
              </motion.div>

              <motion.h1
                className="font-black leading-none mb-8 tracking-tight"
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2, duration: 0.6 }}
              >
                <span className="block text-6xl sm:text-7xl lg:text-8xl text-white uppercase">Аренда</span>
                <span className="block text-6xl sm:text-7xl lg:text-8xl gradient-text uppercase">Спецтехники</span>
                <span className="block text-xl sm:text-2xl text-gray-400 font-medium mt-4 normal-case tracking-normal">
                  Экскаваторы · Краны · Бульдозеры · Погрузчики
                </span>
              </motion.h1>

              <motion.p
                className="text-gray-400 text-lg mb-10 leading-relaxed max-w-lg"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.35, duration: 0.5 }}
              >
                Профессиональная техника мировых брендов на объект по всей России. Доставка, опытные операторы, страхование — всё включено.
              </motion.p>

              <motion.div
                className="flex flex-wrap gap-4 mb-12"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.45, duration: 0.5 }}
              >
                <Link to="/catalog">
                  <motion.div whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}>
                    <Button size="lg" variant="primary" className="gap-2 uppercase tracking-wide">
                      Открыть каталог <ChevronRight size={18} />
                    </Button>
                  </motion.div>
                </Link>
                <Link to="/wizard">
                  <motion.div whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}>
                    <Button size="lg" variant="secondary" className="gap-2">
                      <Zap size={16} /> Мастер подбора
                    </Button>
                  </motion.div>
                </Link>
                <a href="tel:+74951234567">
                  <motion.div whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}>
                    <Button size="lg" variant="ghost" className="gap-2 text-white border border-white/15 hover:border-white/30">
                      <Phone size={16} /> Позвонить
                    </Button>
                  </motion.div>
                </a>
              </motion.div>

              <motion.div
                className="flex flex-wrap gap-6"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.6, duration: 0.5 }}
              >
                {[
                  { icon: Shield, text: 'Полное страхование' },
                  { icon: Truck, text: 'Доставка на объект' },
                  { icon: Wrench, text: 'Тех. поддержка 24/7' },
                ].map(({ icon: Icon, text }) => (
                  <div key={text} className="flex items-center gap-2 text-sm text-gray-500">
                    <Icon size={13} className="text-amber-500" />
                    {text}
                  </div>
                ))}
              </motion.div>
            </div>
          </div>

          <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 opacity-30">
            <div className="w-5 h-8 border border-gray-500 rounded-full flex items-start justify-center pt-1.5">
              <div className="w-1 h-2 bg-amber-400 rounded-full animate-bounce" />
            </div>
          </div>
        </section>

        {/* ─── STATS ─── */}
        <section className="bg-[#111111] border-y border-white/6">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="grid grid-cols-2 md:grid-cols-4">
              {stats.map((stat, i) => {
                const Icon = stat.icon
                return (
                  <motion.div
                    key={stat.label}
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.1, duration: 0.4 }}
                    className={`flex items-center gap-4 py-8 px-6 ${i < stats.length - 1 ? 'border-r border-white/6' : ''}`}
                  >
                    <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
                      <Icon size={18} className="text-amber-400" />
                    </div>
                    <div>
                      <div className="text-2xl font-black text-white">{stat.value}</div>
                      <div className="text-xs text-gray-500 mt-0.5">{stat.label}</div>
                    </div>
                  </motion.div>
                )
              })}
            </div>
          </div>
        </section>

        {/* ─── HOW IT WORKS ─── */}
        <section className="py-24">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <motion.div
              className="text-center mb-16"
              initial="hidden" whileInView="show" viewport={{ once: true }}
              variants={inView}
            >
              <p className="text-xs text-amber-500 font-semibold uppercase tracking-[0.2em] mb-3">Как мы работаем</p>
              <h2 className="text-4xl sm:text-5xl font-black text-white mb-4">
                Три шага до <span className="gradient-text">техники на объекте</span>
              </h2>
              <p className="text-gray-500 max-w-md mx-auto">Простой процесс аренды без бюрократии и лишних звонков</p>
            </motion.div>

            <div className="grid md:grid-cols-3 gap-8">
              {steps.map((step, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 30 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.15, duration: 0.5 }}
                  whileHover={{ y: -6, transition: { duration: 0.2 } }}
                  className="bg-[#111111] border border-white/6 rounded-xl p-8 cursor-default hover:border-amber-500/20 transition-colors"
                >
                  <div className="text-5xl font-black gradient-text mb-6 leading-none">{step.num}</div>
                  <h3 className="text-lg font-bold text-white mb-3">{step.title}</h3>
                  <p className="text-gray-500 text-sm leading-relaxed">{step.desc}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── CATEGORIES ─── */}
        <section className="py-24 bg-[#0D0D0D]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <motion.div
              className="flex items-end justify-between mb-12"
              initial="hidden" whileInView="show" viewport={{ once: true }}
              variants={inView}
            >
              <div>
                <p className="text-xs text-amber-500 font-semibold uppercase tracking-[0.2em] mb-3">Парк техники</p>
                <h2 className="text-4xl sm:text-5xl font-black text-white">
                  Категории <span className="gradient-text">техники</span>
                </h2>
              </div>
              <Link to="/catalog" className="hidden md:flex items-center gap-2 text-sm text-amber-400 hover:text-amber-300 transition-colors font-medium">
                Весь каталог <ArrowRight size={16} />
              </Link>
            </motion.div>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {categoryList.map((cat, i) => (
                <motion.div
                  key={cat.name}
                  initial={{ opacity: 0, scale: 0.95 }}
                  whileInView={{ opacity: 1, scale: 1 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.08, duration: 0.4 }}
                >
                  <Link
                    to={`/catalog?category=${encodeURIComponent(cat.name)}`}
                    className="group relative overflow-hidden rounded-xl block border border-white/6 hover:border-amber-500/30 transition-all duration-300"
                    style={{ aspectRatio: '4/3' }}
                  >
                    <motion.img
                      src={cat.img}
                      alt={cat.name}
                      className="w-full h-full object-cover"
                      whileHover={{ scale: 1.08 }}
                      transition={{ duration: 0.5 }}
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/30 to-transparent" />
                    <motion.div
                      className="absolute inset-0 bg-amber-500/0"
                      whileHover={{ backgroundColor: 'rgba(245,158,11,0.07)' }}
                      transition={{ duration: 0.25 }}
                    />
                    <div className="absolute bottom-0 left-0 right-0 p-4">
                      <h3 className="text-sm font-bold text-white group-hover:text-amber-300 transition-colors">{cat.name}</h3>
                      <div className="flex items-center justify-between mt-1">
                        <p className="text-xs text-gray-400">{cat.count} единиц</p>
                        <motion.div
                          initial={{ x: 0 }}
                          whileHover={{ x: 4 }}
                          transition={{ duration: 0.2 }}
                        >
                          <ArrowRight size={14} className="text-gray-500 group-hover:text-amber-400 transition-colors" />
                        </motion.div>
                      </div>
                    </div>
                  </Link>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── FEATURED ─── */}
        <section className="py-24">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <motion.div
              className="flex items-end justify-between mb-12"
              initial="hidden" whileInView="show" viewport={{ once: true }}
              variants={inView}
            >
              <div>
                <p className="text-xs text-amber-500 font-semibold uppercase tracking-[0.2em] mb-3">Популярные позиции</p>
                <h2 className="text-4xl sm:text-5xl font-black text-white">
                  Топ <span className="gradient-text">аренды</span>
                </h2>
                <p className="text-gray-500 mt-2">Наиболее востребованная техника прямо сейчас</p>
              </div>
              <Link to="/catalog" className="hidden md:block">
                <motion.div whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}>
                  <Button variant="secondary" className="gap-2">Весь каталог <ArrowRight size={16} /></Button>
                </motion.div>
              </Link>
            </motion.div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {featured.map((eq, i) => (
                <EquipmentCard key={eq.id} equipment={eq} index={i} />
              ))}
            </div>
          </div>
        </section>

        {/* ─── ADVANTAGES ─── */}
        <section className="py-24 bg-[#0D0D0D]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="grid lg:grid-cols-2 gap-16 items-center">
              <motion.div
                initial="hidden" whileInView="show" viewport={{ once: true }}
                variants={inView}
              >
                <p className="text-xs text-amber-500 font-semibold uppercase tracking-[0.2em] mb-3">Почему мы</p>
                <h2 className="text-4xl sm:text-5xl font-black text-white mb-6">
                  Надёжный партнёр<br />
                  <span className="gradient-text">для вашего проекта</span>
                </h2>
                <p className="text-gray-400 leading-relaxed mb-10">
                  15 лет на рынке строительной техники. Собственный парк более 500 единиц, штат сертифицированных операторов, полное страхование и официальный документооборот.
                </p>
                <Link to="/about">
                  <motion.div whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}>
                    <Button variant="secondary" className="gap-2">О компании <ArrowRight size={16} /></Button>
                  </motion.div>
                </Link>
              </motion.div>
              <div className="grid grid-cols-2 gap-4">
                {advantages.map((adv, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, scale: 0.9 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.1, duration: 0.4 }}
                    whileHover={{ y: -4, transition: { duration: 0.2 } }}
                    className="bg-[#111111] border border-white/6 rounded-xl p-6 hover:border-amber-500/20 transition-colors cursor-default"
                  >
                    <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center mb-4">
                      <div className="w-2 h-2 rounded-full bg-amber-400" />
                    </div>
                    <h3 className="text-sm font-bold text-white mb-2">{adv.title}</h3>
                    <p className="text-xs text-gray-500 leading-relaxed">{adv.desc}</p>
                  </motion.div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ─── WIZARD CTA ─── */}
        <section className="py-24 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-r from-amber-500/5 via-transparent to-transparent" />
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-transparent via-amber-500/60 to-transparent" />
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex flex-col lg:flex-row items-center gap-16">
              <motion.div
                className="flex-1"
                initial="hidden" whileInView="show" viewport={{ once: true }}
                variants={inView}
              >
                <div className="inline-flex items-center gap-2 bg-amber-500/10 border border-amber-500/25 rounded-sm px-4 py-1.5 mb-6">
                  <Zap size={13} className="text-amber-400" />
                  <span className="text-xs text-amber-300 font-semibold uppercase tracking-[0.15em]">ИИ-подбор за 30 секунд</span>
                </div>
                <h2 className="text-4xl sm:text-5xl font-black text-white mb-5">
                  Мастер подбора<br />
                  <span className="gradient-text">проектной конфигурации</span>
                </h2>
                <p className="text-gray-400 mb-8 leading-relaxed max-w-lg">
                  Опишите ваш проект — тип работ, площадь, сроки, рельеф — и система автоматически подберёт оптимальный пакет техники с расчётом стоимости.
                </p>
                <ul className="space-y-3 mb-10">
                  {[
                    'Анализ параметров проекта за несколько секунд',
                    'Оптимальный набор техники под конкретные условия',
                    'Экономия до 25% против раздельной аренды',
                    'Мгновенное бронирование всего пакета одним кликом',
                  ].map((item, i) => (
                    <motion.li
                      key={item}
                      className="flex items-start gap-3 text-sm text-gray-400"
                      initial={{ opacity: 0, x: -16 }}
                      whileInView={{ opacity: 1, x: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: 0.1 + i * 0.08 }}
                    >
                      <CheckCircle size={15} className="text-amber-500 shrink-0 mt-0.5" />
                      {item}
                    </motion.li>
                  ))}
                </ul>
                <Link to="/wizard">
                  <motion.div whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}>
                    <Button size="lg" className="gap-2 uppercase tracking-wide">
                      <Zap size={16} /> Запустить мастер подбора
                    </Button>
                  </motion.div>
                </Link>
              </motion.div>

              <div className="flex-shrink-0">
                <div className="w-64 h-64 relative">
                  <div className="absolute inset-0 rounded-full border border-amber-500/15 scanner-ping" />
                  <div className="absolute inset-6 rounded-full border border-amber-500/25 scanner-ping-2" />
                  <div className="absolute inset-12 rounded-full border border-amber-500/35 scanner-ping-3" />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <motion.div
                      className="w-24 h-24 bg-amber-500/8 border border-amber-500/25 rounded-full flex items-center justify-center"
                      animate={{ scale: [1, 1.05, 1] }}
                      transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
                    >
                      <Zap size={40} className="text-amber-400" />
                    </motion.div>
                  </div>
                  <div
                    className="absolute inset-0 rounded-full border border-transparent scanner-rotate"
                    style={{ borderTopColor: 'rgba(245,158,11,0.6)' }}
                  />
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── TESTIMONIALS ─── */}
        <section className="py-24 bg-[#0D0D0D]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <motion.div
              className="text-center mb-14"
              initial="hidden" whileInView="show" viewport={{ once: true }}
              variants={inView}
            >
              <p className="text-xs text-amber-500 font-semibold uppercase tracking-[0.2em] mb-3">Отзывы</p>
              <h2 className="text-4xl sm:text-5xl font-black text-white">
                Что говорят <span className="gradient-text">клиенты</span>
              </h2>
            </motion.div>

            <div className="grid md:grid-cols-3 gap-6">
              {testimonials.map((t, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 24 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.12, duration: 0.45 }}
                  whileHover={{ y: -4, transition: { duration: 0.2 } }}
                  className="bg-[#111111] border border-white/6 rounded-xl p-7 hover:border-amber-500/20 transition-colors cursor-default"
                >
                  <div className="flex items-center gap-0.5 mb-5">
                    {Array.from({ length: 5 }).map((_, j) => (
                      <Star key={j} size={14} className={j < t.rating ? 'text-amber-400 fill-amber-400' : 'text-gray-700'} />
                    ))}
                  </div>
                  <p className="text-gray-400 text-sm leading-relaxed mb-6">«{t.text}»</p>
                  <div className="pt-4 border-t border-white/6">
                    <div className="text-sm font-semibold text-gray-200">{t.name}</div>
                    <div className="text-xs text-gray-600 mt-0.5">{t.company}</div>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── FINAL CTA ─── */}
        <section className="py-24 relative overflow-hidden">
          <div className="absolute inset-0">
            <div
              className="absolute inset-0 bg-cover bg-center opacity-10"
              style={{ backgroundImage: 'url(https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=1920&auto=format&fit=crop&q=80)' }}
            />
            <div className="absolute inset-0 bg-gradient-to-t from-[#0A0A0A] via-[#0A0A0A]/80 to-[#0A0A0A]" />
          </div>
          <motion.div
            className="relative max-w-3xl mx-auto px-4 text-center"
            initial="hidden" whileInView="show" viewport={{ once: true }}
            variants={inView}
          >
            <h2 className="text-4xl sm:text-5xl font-black text-white mb-4">
              Нужна <span className="gradient-text">консультация?</span>
            </h2>
            <p className="text-gray-500 text-lg mb-10">
              Наши специалисты помогут подобрать технику, рассчитают стоимость и ответят на все вопросы
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <motion.div whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}>
                <a href="tel:+74951234567">
                  <Button size="lg" variant="primary" className="gap-2 uppercase tracking-wide">
                    <Phone size={16} /> +7 (495) 123-45-67
                  </Button>
                </a>
              </motion.div>
              <motion.div whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}>
                <Link to="/contact">
                  <Button size="lg" variant="secondary" className="gap-2">
                    Оставить заявку <ArrowRight size={16} />
                  </Button>
                </Link>
              </motion.div>
            </div>
            <p className="text-gray-700 text-xs mt-8">Работаем Пн–Пт 8:00–19:00 · Экстренная линия 24/7</p>
          </motion.div>
        </section>

      </div>
    </PageTransition>
  )
}
