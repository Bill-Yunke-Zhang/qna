import { cn } from '../../lib/utils';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'success' | 'warning' | 'outline' | 'ai';
}

export function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        variant === 'default' && 'bg-accent-soft text-accent-ink',
        variant === 'success' && 'bg-success-soft text-success-ink',
        variant === 'warning' && 'bg-warning-soft text-warning-ink',
        variant === 'outline' && 'border border-line-strong text-ink-secondary',
        variant === 'ai' && 'bg-ai-soft text-ai-ink',
        className
      )}
      {...props}
    />
  );
}
