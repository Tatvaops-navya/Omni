import clsx from 'clsx'
import { Moon, Sun } from 'lucide-react'
import { useTheme } from '../theme/ThemeProvider'

export default function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <div
      className={clsx(
        'inline-flex items-center p-1 rounded-full border transition-colors',
        isDark
          ? 'bg-navy-900/80 border-slate-700/60'
          : 'bg-slate-100 border-slate-200',
        className,
      )}
      role="group"
      aria-label="Theme"
    >
      <button
        type="button"
        aria-label="Light mode"
        aria-pressed={!isDark}
        onClick={() => setTheme('light')}
        className={clsx(
          'p-2 rounded-full transition-all duration-200',
          !isDark
            ? 'bg-white text-amber-500 shadow-sm'
            : 'text-slate-400 hover:text-slate-200',
        )}
      >
        <Sun className="w-4 h-4" />
      </button>
      <button
        type="button"
        aria-label="Dark mode"
        aria-pressed={isDark}
        onClick={() => setTheme('dark')}
        className={clsx(
          'p-2 rounded-full transition-all duration-200',
          isDark
            ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-500/30'
            : 'text-slate-400 hover:text-slate-600',
        )}
      >
        <Moon className="w-4 h-4" />
      </button>
    </div>
  )
}
