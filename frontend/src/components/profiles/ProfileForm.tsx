import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router';
import Alert from '../common/Alert';
import Button from '../common/Button';
import FormField from '../common/FormField';
import Input from '../common/Input';
import CitySelect from './CitySelect';
import Textarea from '../common/Textarea';
import { profileErrorMessage } from '../../features/profiles/errors';
import { useUpdateProfile } from '../../features/profiles/hooks';
import { profileFormSchema, type ProfileFormValues } from '../../features/profiles/schemas';
import type { MyProfile } from '../../features/profiles/types';

export default function ProfileForm({ profile }: { profile: MyProfile }) {
  const mutation = useUpdateProfile();
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileFormSchema),
    defaultValues: {
      displayName: profile.displayName ?? '',
      bio: profile.bio ?? '',
      city: profile.citySlug ?? '',
    },
  });

  useEffect(() => {
    reset({
      displayName: profile.displayName ?? '',
      bio: profile.bio ?? '',
      city: profile.citySlug ?? '',
    });
  }, [profile, reset]);

  async function submit(values: ProfileFormValues) {
    try {
      await mutation.mutateAsync({
        displayName: values.displayName,
        bio: values.bio || null,
        // An unchanged historical city need not be reassigned when editing a bio.
        ...(values.city !== profile.citySlug ? { city: values.city } : {}),
      });
      navigate('/profile', { replace: true, state: { profileUpdated: true } });
    } catch {
      // The mutation state renders a safe, normalized error message.
    }
  }

  const bioLength = useWatch({ control, name: 'bio' })?.length ?? 0;
  const selectedCity = useWatch({ control, name: 'city' }) ?? '';
  return (
    <form className="space-y-5" onSubmit={handleSubmit(submit)} noValidate>
      {mutation.isError && <Alert>{profileErrorMessage(mutation.error)}</Alert>}
      <FormField id="display-name" label="Display name" error={errors.displayName?.message}>
        <Input
          id="display-name"
          autoComplete="nickname"
          aria-describedby={errors.displayName ? 'display-name-error' : undefined}
          aria-invalid={Boolean(errors.displayName)}
          {...register('displayName')}
        />
      </FormField>
      <FormField
        id="bio"
        label="Bio (optional)"
        error={errors.bio?.message}
        hint={`${bioLength}/300 characters`}
      >
        <Textarea
          id="bio"
          rows={5}
          aria-describedby={errors.bio ? 'bio-error' : 'bio-hint'}
          aria-invalid={Boolean(errors.bio)}
          placeholder="Share a little about yourself and what brings you to UniShop."
          {...register('bio')}
        />
      </FormField>
      <FormField id="city" label="City" error={errors.city?.message}>
        <CitySelect id="city" registration={register('city')} value={selectedCity} currentSlug={profile.citySlug} currentName={profile.city} />
      </FormField>
      <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:justify-end">
        <Button variant="secondary" onClick={() => navigate('/profile')}>Cancel</Button>
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? 'Saving…' : 'Save profile'}
        </Button>
      </div>
    </form>
  );
}
