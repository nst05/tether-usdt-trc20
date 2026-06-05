import React, { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { MessageCircle, X, Send } from 'lucide-react'

interface Message {
  id: number
  text: string
  sender: 'user' | 'support'
  time: string
}

const AUTO_RESPONSES = [
  'Здравствуйте! Рады помочь вам с выбором техники.',
  'Наши менеджеры свяжутся с вами в течение 15 минут.',
  'Вы можете оставить контактный номер и мы перезвоним.',
  'Для срочных вопросов звоните: +7 (495) 123-45-67',
]

let msgIdCounter = 0

function getTime() {
  return new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

export const ChatWidget: React.FC = () => {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const [autoIndex, setAutoIndex] = useState(0)
  const [unread, setUnread] = useState(false)
  const [initialized, setInitialized] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const addMessage = (text: string, sender: 'user' | 'support') => {
    msgIdCounter++
    setMessages((prev) => [...prev, { id: msgIdCounter, text, sender, time: getTime() }])
  }

  // Initial greeting when chat opens
  useEffect(() => {
    if (open && !initialized) {
      setInitialized(true)
      setTimeout(() => {
        addMessage('Здравствуйте! Чем могу помочь?', 'support')
      }, 500)
    }
  }, [open, initialized])

  // Auto scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = () => {
    const text = inputValue.trim()
    if (!text) return
    addMessage(text, 'user')
    setInputValue('')

    // Auto response after 800ms
    setTimeout(() => {
      const response = AUTO_RESPONSES[autoIndex % AUTO_RESPONSES.length]
      setAutoIndex((prev) => prev + 1)
      addMessage(response, 'support')
      if (!open) {
        setUnread(true)
      }
    }, 800)
  }

  const handleOpen = () => {
    setOpen(true)
    setUnread(false)
  }

  const handleClose = () => {
    setOpen(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {/* Chat panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="w-80 bg-[#111111] border border-white/10 rounded-2xl overflow-hidden shadow-2xl"
          >
            {/* Header */}
            <div className="bg-[#1A1A1A] border-b border-white/8 px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-sm font-semibold text-white">Онлайн-поддержка</span>
              </div>
              <button
                onClick={handleClose}
                className="w-7 h-7 flex items-center justify-center rounded-full text-gray-500 hover:text-white hover:bg-white/10 transition-all cursor-pointer"
              >
                <X size={15} />
              </button>
            </div>

            {/* Messages */}
            <div className="h-72 overflow-y-auto p-4 flex flex-col gap-3">
              {messages.length === 0 && (
                <div className="flex items-center justify-center h-full text-center">
                  <p className="text-xs text-gray-600">Напишите ваш вопрос</p>
                </div>
              )}
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex flex-col gap-0.5 ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}
                >
                  <div
                    className={`max-w-[80%] px-3 py-2 rounded-xl text-sm ${
                      msg.sender === 'user'
                        ? 'bg-amber-500 text-black font-medium'
                        : 'bg-[#1A1A1A] text-gray-200 border border-white/6'
                    }`}
                  >
                    {msg.text}
                  </div>
                  <span className="text-[10px] text-gray-700">{msg.time}</span>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="border-t border-white/8 p-3 flex gap-2">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Введите сообщение..."
                className="flex-1 bg-[#1A1A1A] border border-white/8 text-gray-200 text-sm rounded-lg px-3 py-2 outline-none focus:border-amber-500/40 transition placeholder:text-gray-600"
              />
              <button
                onClick={handleSend}
                disabled={!inputValue.trim()}
                className="w-9 h-9 flex items-center justify-center bg-amber-500 rounded-lg text-black hover:bg-amber-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shrink-0"
              >
                <Send size={15} />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Toggle button */}
      <motion.button
        onClick={open ? handleClose : handleOpen}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        className="relative w-14 h-14 bg-amber-500 rounded-full flex items-center justify-center shadow-lg shadow-amber-500/30 hover:bg-amber-400 transition-colors cursor-pointer"
      >
        <AnimatePresence mode="wait">
          {open ? (
            <motion.div key="close" initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }} transition={{ duration: 0.15 }}>
              <X size={22} className="text-black" />
            </motion.div>
          ) : (
            <motion.div key="chat" initial={{ rotate: 90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: -90, opacity: 0 }} transition={{ duration: 0.15 }}>
              <MessageCircle size={22} className="text-black" />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Unread dot */}
        {unread && !open && (
          <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full border-2 border-[#0A0A0A]" />
        )}
      </motion.button>
    </div>
  )
}
