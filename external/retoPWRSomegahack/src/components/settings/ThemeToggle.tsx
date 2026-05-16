'use client';

import { useTheme } from '@/components/shared/ThemeProvider';
import { Sun, Moon, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ThemeToggleProps {
  variant?: 'card' | 'switch';
}

export default function ThemeToggle({ variant = 'card' }: ThemeToggleProps) {
  const { theme, setTheme, toggleTheme } = useTheme();

  if (variant === 'switch') {
    return (
      <button
        onClick={toggleTheme}
        className="relative inline-flex h-6 w-11 items-center rounded-full bg-gov-gray-200 dark:bg-dark-accent transition-colors focus:outline-none focus:ring-2 focus:ring-gov-blue-500 focus:ring-offset-2 dark:focus:ring-offset-dark-bg"
      >
        <span
          className={cn(
            "inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200",
            theme === 'dark' ? "translate-x-6" : "translate-x-1"
          )}
        >
          {theme === 'light' ? (
            <Sun size={10} className="text-gov-gold-500 m-0.5" />
          ) : (
            <Moon size={10} className="text-gov-blue-700 m-0.5" />
          )}
        </span>
      </button>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {/* CARD MODO CLARO */}
      <div 
        onClick={() => setTheme('light')}
        className={cn(
          "relative bg-white border-2 rounded-2xl p-5 cursor-pointer transition-all duration-300 group overflow-hidden",
          theme === 'light' 
            ? "border-gov-blue-700 shadow-xl shadow-gov-blue-700/10 scale-[1.02]" 
            : "border-gov-gray-100 opacity-60 hover:opacity-100 hover:border-gov-gray-300"
        )}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
             <div className="p-2 bg-gov-gold-100 rounded-lg text-gov-gold-500">
               <Sun size={18} />
             </div>
             <span className="font-bold text-gov-gray-900 group-hover:text-gov-blue-700 transition-colors">Modo Claro</span>
          </div>
          {theme === 'light' && <CheckCircle2 size={18} className="text-sem-green fill-sem-green-bg" />}
        </div>
        
        {/* Mock UI Preview - Light */}
        <div className="h-24 bg-gov-gray-50 rounded-xl border border-gov-gray-100 p-2 space-y-2 overflow-hidden">
           <div className="flex gap-2 h-full">
              <div className="w-1/4 bg-gov-blue-900 rounded-lg" />
              <div className="flex-1 space-y-2">
                 <div className="h-3 bg-white rounded-md shadow-sm" />
                 <div className="h-8 bg-white rounded-lg shadow-sm border border-gov-gray-100" />
              </div>
           </div>
        </div>
      </div>

      {/* CARD MODO OSCURO */}
      <div 
        onClick={() => setTheme('dark')}
        className={cn(
          "relative bg-dark-surface border-2 rounded-2xl p-5 cursor-pointer transition-all duration-300 group overflow-hidden",
          theme === 'dark' 
            ? "border-dark-cyan shadow-xl shadow-dark-cyan/10 scale-[1.02]" 
            : "border-dark-border opacity-40 hover:opacity-100 hover:border-dark-accent"
        )}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
             <div className="p-2 bg-dark-accent/20 rounded-lg text-dark-cyan">
               <Moon size={18} />
             </div>
             <span className="font-bold text-dark-text group-hover:text-dark-cyan transition-colors">Modo Oscuro</span>
          </div>
          {theme === 'dark' && <CheckCircle2 size={18} className="text-dark-cyan fill-dark-accent/10" />}
        </div>

        {/* Mock UI Preview - Dark */}
        <div className="h-24 bg-dark-bg rounded-xl border border-dark-border p-2 space-y-2 overflow-hidden">
           <div className="flex gap-2 h-full">
              <div className="w-1/4 bg-dark-sidebar rounded-lg" />
              <div className="flex-1 space-y-2">
                 <div className="h-3 bg-dark-surface rounded-md border border-dark-border" />
                 <div className="h-8 bg-dark-surface rounded-lg border border-dark-border shadow-inner" />
              </div>
           </div>
        </div>
      </div>
    </div>
  );
}
