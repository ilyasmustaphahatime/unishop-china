export type MyProfile = {
  publicHandle: string;
  displayName: string | null;
  bio: string | null;
  city: string | null;
  citySlug: string | null;
  cityActive: boolean;
  onboardingCompleted: boolean;
  memberSince: string;
  createdAt: string;
  updatedAt: string;
  emailVerified: boolean;
  phoneVerified: boolean;
};

export type PublicProfile = Pick<
  MyProfile,
  | 'publicHandle'
  | 'displayName'
  | 'bio'
  | 'city'
  | 'memberSince'
  | 'emailVerified'
  | 'phoneVerified'
> & {
  displayName: string;
  city: string;
  sellerVerified: boolean;
};

export type UpdateProfileInput = {
  displayName?: string | null;
  bio?: string | null;
  city?: string | null;
};
