import { forwardRef, type SelectHTMLAttributes } from 'react';

const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className = '', ...props }, ref) {
    return (
      <select
        ref={ref}
        className={`w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-950 outline-none transition focus:border-red-500 focus:ring-4 focus:ring-red-100 disabled:bg-slate-100 ${className}`}
        {...props}
      />
    );
  },
);

export default Select;
