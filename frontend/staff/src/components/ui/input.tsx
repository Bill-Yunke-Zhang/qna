import { cn } from '../../lib/utils';

type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export function Input({ className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        'w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2',
        'text-slate-100 placeholder-slate-400',
        'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
        className
      )}
      {...props}
    />
  );
}
