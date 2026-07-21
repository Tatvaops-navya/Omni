import clsx from 'clsx'
import { Mail } from 'lucide-react'
import type { UtmSourceKey } from '../data/leadAcquisition'

type Props = {
  source: UtmSourceKey
  className?: string
}

export default function SourceBrandIcon({ source, className }: Props) {
  const box = clsx(
    'w-5 h-5 rounded-md flex items-center justify-center shrink-0 overflow-hidden',
    className,
  )

  switch (source) {
    case 'google':
      return (
        <span className={clsx(box, 'bg-white ring-1 ring-[var(--divider)]')} aria-hidden>
          <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" role="img">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
        </span>
      )
    case 'facebook':
      return (
        <span className={clsx(box, 'bg-[#1877F2]')} aria-hidden>
          <svg viewBox="0 0 24 24" className="w-3.5 h-3.5 fill-white" role="img">
            <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
          </svg>
        </span>
      )
    case 'linkedin':
      return (
        <span className={clsx(box, 'bg-[#0A66C2]')} aria-hidden>
          <svg viewBox="0 0 24 24" className="w-3.5 h-3.5 fill-white" role="img">
            <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
          </svg>
        </span>
      )
    case 'youtube':
      return (
        <span className={clsx(box, 'bg-[#FF0000]')} aria-hidden>
          <svg viewBox="0 0 24 24" className="w-3.5 h-3.5 fill-white" role="img">
            <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
          </svg>
        </span>
      )
    case 'newsletter':
      return (
        <span className={clsx(box, 'bg-fuchsia-500/20 text-fuchsia-400')} aria-hidden>
          <Mail className="w-3.5 h-3.5" />
        </span>
      )
    case 'twitter':
      return (
        <span className={clsx(box, 'bg-black text-white dark:bg-white dark:text-black')} aria-hidden>
          <svg viewBox="0 0 24 24" className="w-3 h-3 fill-current" role="img">
            <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
          </svg>
        </span>
      )
    default:
      return null
  }
}
