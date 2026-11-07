import { createHash } from 'node:crypto';
import autoprefixer from 'autoprefixer';
import postcss from 'postcss';
import tailwind from 'tailwindcss';
import nesting from 'tailwindcss/nesting/index.js';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';

const raw = 'flex rtl:space-x-reverse space-x-4 ltr:text-left rtl:text-right md:grid-cols-2 hover:bg-blue-500 focus-visible:ring-2 dark:text-white group-hover:underline peer-checked:block [&>span]:font-bold w-[37px] data-[state=open]:block';

describe('security dependency compatibility', () => {
  // Hashes were captured with Tailwind 3.4.19 / selector-parser 6.1.4 before
  // the scoped parser override. They protect CSS semantics, not just compilation.
  it.each([
    {
      nested: false,
      css: '@tailwind base; @tailwind components; @tailwind utilities; .probe:hover > span { @apply text-red-500; }',
      expected: '6e2b67bccc673f409ccaa71f1c93f27e1c5580c3b7df9eae99b413a3b0992499',
    },
    {
      nested: true,
      css: '@tailwind base; @tailwind components; @tailwind utilities; .probe { &:hover { @apply text-red-500; } & > span { @apply font-bold; } }',
      expected: '5dfc4d9a784151c015af8a680cf40c2a0582fbdb8bda790b83f12f812f7b041f',
    },
  ])('preserves variants, RTL and nested=$nested CSS', async ({ nested, css, expected }) => {
    const plugins = [
      ...(nested ? [nesting()] : []),
      tailwind({ content: [{ raw, extension: 'html' }], darkMode: 'class' }),
      autoprefixer(),
    ];
    const result = await postcss(plugins).process(css, { from: undefined });
    expect(createHash('sha256').update(result.css).digest('hex')).toBe(expected);
  });

  it('rejects oversized constrained arrays without allocating a per-item error list', () => {
    const result = z.array(z.string()).max(2).safeParse(Array(5000).fill(null));
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues).toHaveLength(1);
      expect(result.error.issues[0].code).toBe('too_big');
    }
  });
});
