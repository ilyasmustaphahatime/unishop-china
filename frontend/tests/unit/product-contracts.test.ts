import { describe, expect, it } from 'vitest';
import { productInputSchema, productSlugSchema, ownProductSchema, publicProductSchema } from '../../src/features/products/schemas';
import { safeInternalPath } from '../../src/routes/routePaths';
import { productErrorMessage } from '../../src/features/products/api';
import { AxiosError } from 'axios';

const input = { title: 'Study desk', description: 'A desk in good condition.', price: '123.45',
  condition: 'good', city_slug: 'qingdao', category_slug: 'study' };
const city = { slug: 'qingdao', name_en: 'Qingdao', name_zh: '青岛', province_en: 'Shandong', province_zh: '山东', country_code: 'CN' };
const category = { slug: 'study', name_en: 'Study', name_zh: '学习', description: null, parent_slug: null };
const publicProduct = {
  public_slug: 'item-' + 'a'.repeat(24), title: 'Study desk', description: input.description, price: '123.45',
  currency: 'CNY', condition: 'good', city, category, published_at: '2026-10-08T00:00:00Z',
  status: 'PUBLISHED', seller: { public_handle: 'user-seller123', display_name: 'Seller', seller_verified: true },
};

describe('listing contracts', () => {
  it.each(['0', '0.00', '-1', '1e3', 'NaN', 'Infinity', '01', '1.001', '10000000000', ' 1', '.5'])('rejects unsafe price %s', (price) => {
    expect(productInputSchema.safeParse({ ...input, price }).success).toBe(false);
  });
  it.each(['0.01', '10', '10.1', '9999999999.99'])('accepts exact decimal input %s', (price) => {
    expect(productInputSchema.parse({ ...input, price }).price).toBe(price);
  });
  it('accepts normalized Unicode and keeps HTML-shaped plain text inert', () => {
    const parsed = productInputSchema.parse({ ...input, title: ' Cafe\u0301 桌子 😀 ', description: '<script>alert(1)</script>' });
    expect(parsed.title).toBe('Café 桌子 😀');
    expect(parsed.description).toBe('<script>alert(1)</script>');
  });
  it.each(['bad\u202etitle', 'bad\x00title', '\uD800broken', 'a', 'a'.repeat(121)])('rejects unsupported title', (title) => {
    expect(productInputSchema.safeParse({ ...input, title }).success).toBe(false);
  });
  it.each(['seller_user_id', 'public_slug', 'status', 'currency', 'city_id', 'images'])('rejects writable extra %s', (field) => {
    expect(productInputSchema.safeParse({ ...input, [field]: 'forged' }).success).toBe(false);
  });
  it.each(['id', 'email', 'phone', 'seller_user_id', 'storage_key', 'evidence', 'roles'])('rejects public private field %s', (field) => {
    expect(publicProductSchema.safeParse({ ...publicProduct, [field]: 'private' }).success).toBe(false);
    expect(publicProductSchema.safeParse({ ...publicProduct, seller: { ...publicProduct.seller, [field]: 'private' } }).success).toBe(false);
  });
  it('uses separate owner and public projections', () => {
    expect(publicProductSchema.parse(publicProduct).seller.seller_verified).toBe(true);
    const { seller: _, ...fields } = publicProduct;
    void _;
    const own = { ...fields, status: 'DRAFT', published_at: null, city_active: true, category_active: true,
      created_at: '2026-10-08T00:00:00Z', updated_at: '2026-10-08T00:00:00Z' };
    expect(ownProductSchema.parse(own).status).toBe('DRAFT');
    expect(publicProductSchema.safeParse(own).success).toBe(false);
  });
  it.each(['../item', 'item-A' + 'a'.repeat(23), 'item-' + 'a'.repeat(23), 'item-' + 'a'.repeat(24) + '?token=private'])('rejects invalid public reference', (slug) => {
    expect(productSlugSchema.safeParse(slug).success).toBe(false);
  });
  it('keeps navigation strict and token-free', () => {
    const slug = publicProduct.public_slug;
    expect(safeInternalPath('/sell/new', '/profile')).toBe('/sell/new');
    expect(safeInternalPath('/seller/listings/' + slug + '/edit', '/profile')).toContain(slug);
    expect(safeInternalPath('/p/' + slug, '/profile')).toBe('/p/' + slug);
    for (const path of ['/p/' + slug + '?token=x', '/seller/listings/' + slug + '/edit#token', '//evil.test', '/p/%61']) {
      expect(safeInternalPath(path, '/profile')).toBe('/profile');
    }
  });
  it('never displays driver or attacker controlled error strings', () => {
    const error = new AxiosError('PRIVATE DRIVER ERROR');
    expect(productErrorMessage(error)).not.toContain('PRIVATE');
  });
  it.each(['\n', '\r', '\u2028', '\u2029'])('rejects a trailing line terminator in listing references and prices', (ending) => {
    expect(productSlugSchema.safeParse(publicProduct.public_slug + ending).success).toBe(false);
    expect(productInputSchema.safeParse({ ...input, price: input.price + ending }).success).toBe(false);
    expect(publicProductSchema.safeParse({ ...publicProduct, price: publicProduct.price + ending }).success).toBe(false);
  });
});
