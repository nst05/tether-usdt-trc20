import React from 'react'
import { ChevronDown } from 'lucide-react'

interface SelectOption {
  value: string
  label: string
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  options: SelectOption[]
}

export const Select: React.FC<SelectProps> = ({ label, error, options, className = '', ...props }) => {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-gray-300 mb-1.5">{label}</label>
      )}
      <div className="relative">
        <select
          className={`w-full appearance-none bg-gray-800 border ${error ? 'border-red-500' : 'border-gray-700 focus:border-amber-500 focus:ring-amber-500/20'} text-gray-100 rounded-lg px-4 py-2.5 text-sm outline-none transition-all duration-200 focus:ring-2 cursor-pointer pr-10 ${className}`}
          {...props}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-gray-800">
              {opt.label}
            </option>
          ))}
        </select>
        <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
      </div>
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  )
}
