import type { OwnProduct } from '../features/products/types';
import type { MessageKey } from './resources';
export const conditionKeys = {
  new: 'products:new', like_new: 'products:likeNew', good: 'products:good', fair: 'products:fair',
} as const satisfies Record<OwnProduct['condition'], MessageKey>;
export const productStatusKeys = {
  DRAFT: 'products:draft', PUBLISHED: 'products:published', PAUSED: 'products:paused', ARCHIVED: 'products:archived',
} as const satisfies Record<OwnProduct['status'], MessageKey>;
export const verificationStatusKeys = {
  PENDING: 'verification:pending', UNDER_REVIEW: 'verification:underReview',
  VERIFIED: 'verification:verified', REJECTED: 'verification:rejected',
} as const;
