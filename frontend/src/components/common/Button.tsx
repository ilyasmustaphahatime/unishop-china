import { forwardRef, type ButtonHTMLAttributes } from 'react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost';
};

const variants = {
  primary: 'bg-red-600 text-white shadow-sm hover:bg-red-700 focus:ring-red-200',
  secondary:
    'border border-slate-300 bg-white text-slate-800 hover:border-red-300 hover:text-red-700 focus:ring-red-100',
  ghost: 'text-slate-700 hover:bg-slate-100 hover:text-red-700 focus:ring-slate-200',
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className = '', variant = 'primary', type = 'button', ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={`inline-flex min-h-11 items-center justify-center rounded-xl px-4 py-2.5 text-sm font-bold transition focus:outline-none focus:ring-4 disabled:cursor-not-allowed disabled:opacity-60 ${variants[variant]} ${className}`}
      {...props}
    />
  );
});

export default Button;
