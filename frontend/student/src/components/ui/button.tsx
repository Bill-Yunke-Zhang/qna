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
        'focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-900',
        'disabled:opacity-50 disabled:pointer-events-none',
        variant === 'default' && 'bg-indigo-600 text-white hover:bg-indigo-500 focus:ring-indigo-500',
        variant === 'outline' && 'border border-slate-600 text-slate-200 hover:bg-slate-700 focus:ring-slate-500',
        variant === 'ghost' && 'text-slate-300 hover:bg-slate-700 hover:text-slate-100',
        variant === 'destructive' && 'bg-red-600 text-white hover:bg-red-500 focus:ring-red-500',
        size === 'sm' && 'px-3 py-1.5 text-sm',
        size === 'md' && 'px-4 py-2 text-base',
        size === 'lg' && 'px-6 py-3 text-lg',
        className
      )}
      {...props}
    />
  );
}
