import { localizeMessage } from '../../i18n/messages';
import { useAppTranslation } from '../../i18n/useAppTranslation';
import type { PropsWithChildren } from 'react';

type FormFieldProps = PropsWithChildren<{
  id: string;
  label: string;
  error?: string;
  hint?: string;
}>;

export default function FormField({ id, label, error, hint, children }: FormFieldProps) {
  useAppTranslation();
  return (
    <div>
      <label className="mb-2 block text-sm font-semibold text-slate-800" htmlFor={id}>
        {label}
      </label>
      {children}
      {error ? (
        <p className="mt-2 text-sm text-red-700" id={`${id}-error`} role="alert">
          {localizeMessage(error, 'validation:fieldInvalid')}
        </p>
      ) : hint ? (
        <p className="mt-2 text-xs leading-5 text-slate-500" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}
