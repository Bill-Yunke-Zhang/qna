import { cn } from '../../lib/utils';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'ghost' | 'destructive';
  size?: 'sm' | 'md' | 'lg';
}

export function Button({ className, variant = 'default', size = 'md', ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded-lg font-semibold transition-colors',
        'focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-canvas',
        'disabled:opacity-50 disabled:pointer-events-none',
        variant === 'default' && 'bg-accent text-on-accent hover:bg-accent-hover focus:ring-focus',
        variant === 'outline' && 'border border-line-strong text-ink hover:bg-surface-hover focus:ring-focus',
        variant === 'ghost' && 'text-ink-secondary hover:bg-surface-hover hover:text-ink',
        variant === 'destructive' && 'bg-danger text-on-accent hover:bg-danger-hover focus:ring-danger',
        size === 'sm' && 'px-3 py-1.5 text-sm',
        size === 'md' && 'px-4 py-2 text-base',
        size === 'lg' && 'px-6 py-3 text-lg',
        className
      )}
      {...props}
    />
  );
}
