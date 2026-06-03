import React, { useEffect } from 'react'
import { Input } from '../../components/ui/Input'
import { Button } from '../../components/ui/Button'

export const Settings: React.FC = () => {
  useEffect(() => {
    document.title = 'Настройки — Админ'
  }, [])

  return (
    <div className="p-6 lg:p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-black text-white">Настройки</h1>
        <p className="text-gray-500 text-sm">Конфигурация системы</p>
      </div>

      <div className="max-w-xl space-y-6">
        <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-5">
          <h2 className="font-bold text-gray-200 mb-4">Контактная информация</h2>
          <div className="space-y-4">
            <Input label="Название компании" defaultValue="ТЕХПРОКАТ" />
            <Input label="Телефон" defaultValue="+7 (495) 123-45-67" />
            <Input label="Email" defaultValue="info@tehprokat.ru" />
            <Input label="Адрес" defaultValue="Москва, ул. Промышленная, 12" />
          </div>
          <div className="mt-4">
            <Button size="sm">Сохранить</Button>
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-5">
          <h2 className="font-bold text-gray-200 mb-4">Уведомления</h2>
          <div className="space-y-3">
            {[
              'Email при новой заявке',
              'Email при изменении статуса',
              'SMS-уведомления клиентам',
              'Отчёты на email (еженедельно)',
            ].map((item) => (
              <label key={item} className="flex items-center gap-3 cursor-pointer">
                <div className="w-10 h-5 bg-amber-500 rounded-full relative">
                  <div className="absolute right-0.5 top-0.5 w-4 h-4 bg-white rounded-full" />
                </div>
                <span className="text-sm text-gray-400">{item}</span>
              </label>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
