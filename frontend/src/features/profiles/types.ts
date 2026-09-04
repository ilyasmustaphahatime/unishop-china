export const supportedCities = [
  'Qingdao',
  'Beijing',
  'Shanghai',
  'Shenzhen',
  'Guangzhou',
  'Hangzhou',
] as const;

export type SupportedCity = (typeof supportedCities)[number];

export type MyProfile = {
  publicId: string;
  displayName: string | null;
  bio: string | null;
  city: SupportedCity | null;
  onboardingCompleted: boolean;
  memberSince: string;
  createdAt: string;
  updatedAt: string;
  emailVerified: boolean;
  phoneVerified: boolean;
};

export type PublicProfile = Pick<
  MyProfile,
  | 'publicId'
  | 'displayName'
  | 'bio'
  | 'city'
  | 'memberSince'
  | 'emailVerified'
  | 'phoneVerified'
> & {
  displayName: string;
  city: SupportedCity;
};

export type UpdateProfileInput = {
  displayName?: string | null;
  bio?: string | null;
  city?: SupportedCity | null;
};
