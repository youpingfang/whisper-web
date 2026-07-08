import * as React from 'react'
import { cn } from '@/lib/utils'

// ---- Card ----
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'rounded-[16px] border border-[var(--color-border-soft)] bg-[var(--color-surface)] p-6',
        'shadow-[0_8px_30px_rgba(0,0,0,0.45)] backdrop-blur-sm transition-colors',
        'hover:border-[var(--color-border-strong)]',
        className,
      )}
      {...props}
    />
  )
}
export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('mb-3', className)} {...props} />
}
export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={cn('text-[18px] font-semibold tracking-wide text-[#f0f0f0]', className)} {...props} />
  )
}
export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('space-y-3', className)} {...props} />
}

// ---- Button ----
const buttonVariants = {
  default:
    'bg-[#f5f5f5] text-[#0a0a0a] font-semibold hover:bg-white active:translate-y-px',
  ghost: 'text-[var(--color-ink-dim)] hover:bg-[var(--color-surface-2)]',
  outline: 'border border-[var(--color-border-soft)] text-[var(--color-ink)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-2)]',
}
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof buttonVariants
}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-[9px] px-4 py-2.5 text-[16px]',
        'transition-[filter,transform,border-color,background-color] duration-150 disabled:opacity-50 disabled:pointer-events-none',
        buttonVariants[variant],
        className,
      )}
      {...props}
    />
  ),
)
Button.displayName = 'Button'

// ---- Badge ----
export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border border-[var(--color-border-soft)]',
        'bg-[rgba(255,255,255,0.08)] px-3 py-0.5 text-[14px] font-normal text-[var(--color-ink)]',
        className,
      )}
      {...props}
    />
  )
}

// ---- Progress ----
export function Progress({ value = 0, className }: { value?: number; className?: string }) {
  return (
    <div className={cn('h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-2)]', className)}>
      <div
        className="h-full rounded-full bg-[#f5f5f5] transition-[width] duration-300"
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  )
}

// ---- Textarea (read-only output) ----
export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      'w-full rounded-[9px] border border-[var(--color-border-soft)] bg-[var(--color-input-bg)] p-4',
      'text-[18px] leading-[1.9] font-normal text-[var(--color-input-fg)] outline-none',
      'focus:border-[var(--color-border-strong)]',
      className,
    )}
    {...props}
  />
))
Textarea.displayName = 'Textarea'
