import { useAppTranslation } from '../../i18n/useAppTranslation';
type AvatarProps = {
  name: string | null;
  size?: 'sm' | 'md' | 'lg';
};

const sizes = { sm: 'h-9 w-9 text-sm', md: 'h-12 w-12 text-base', lg: 'h-24 w-24 text-3xl' };

export default function Avatar({ name, size = 'md' }: AvatarProps) {
  const { t } = useAppTranslation();
  const initials =
    name
      ?.trim()
      .split(/\s+/u)
      .slice(0, 2)
      .map((part) => Array.from(part)[0])
      .join('')
      .toLocaleUpperCase() || 'U';
  return (
    <span
      aria-label={t('common:avatar', { name: name || t('common:defaultUser') })}
      dir="auto"
      className={`inline-flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-red-600 to-rose-500 font-black text-white shadow-sm ${sizes[size]}`}
      role="img"
    >
      {initials}
    </span>
  );
}
