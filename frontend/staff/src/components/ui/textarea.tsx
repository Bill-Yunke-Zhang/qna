import { cn } from '../../lib/utils';

type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

export function Textarea({ className, ...props }: TextareaProps) {
  return (
    <textarea
      className={cn(
        'w-full rounded-lg border border-line-strong bg-surface-raised px-3 py-2',
        'text-ink placeholder-ink-subtle',
        'focus:outline-none focus:ring-2 focus:ring-focus focus:border-transparent',
        className
      )}
      {...props}
    />
  );
}
