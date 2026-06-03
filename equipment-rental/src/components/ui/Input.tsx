import React from 'react'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  icon?: React.ReactNode
}

export const Input: React.FC<InputProps> = ({ label, error, icon, className = '', ...props }) => {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-gray-300 mb-1.5">{label}</label>
      )}
      <div className="relative">
        {icon && (
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">{icon}</div>
        )}
        <input
          className={`w-full bg-gray-800 border ${error ? 'border-red-500 focus:border-red-400 focus:ring-red-400/20' : 'border-gray-700 focus:border-blue-500 focus:ring-blue-500/20'} text-gray-100 rounded-lg px-4 py-2.5 text-sm outline-none transition-all duration-200 focus:ring-2 placeholder:text-gray-500 ${icon ? 'pl-10' : ''} ${className}`}
          {...props}
        />
      </div>
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  )
}
