import { z } from 'zod';
import { catalogSlugSchema } from '../catalog/slugs';

export const categorySchema = z.object({
  slug: catalogSlugSchema,
  name_en: z.string().min(1).max(80),
  name_zh: z.string().min(1).max(80),
  description: z.string().max(500).nullable(),
  parent_slug: catalogSlugSchema.nullable(),
}).strict();
export const categoryTreeSchema = categorySchema.extend({
  children: z.array(categorySchema).max(500),
}).strict();
export const categoryListSchema = z.object({ items: z.array(categoryTreeSchema).max(500) }).strict()
  .refine(({ items }) => {
    const slugs = new Set<string>();
    let count = 0;
    return items.every((root) => {
      if (root.parent_slug !== null || slugs.has(root.slug)) return false;
      slugs.add(root.slug);
      count += 1;
      return root.children.every((child) => {
        count += 1;
        if (child.parent_slug !== root.slug || slugs.has(child.slug)) return false;
        slugs.add(child.slug);
        return count <= 500;
      });
    });
  }, 'Invalid category hierarchy.');
