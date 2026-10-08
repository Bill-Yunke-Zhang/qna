import { cn } from '../../lib/utils';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'success' | 'warning' | 'outline';
}

export function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        variant === 'default' && 'bg-indigo-600/20 text-indigo-300',
        variant === 'success' && 'bg-emerald-600/20 text-emerald-300',
        variant === 'warning' && 'bg-amber-600/20 text-amber-300',
        variant === 'outline' && 'border border-slate-600 text-slate-300',
        className
      )}
      {...props}
    />
  );
}
