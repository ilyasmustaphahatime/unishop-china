import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { Navigate, useNavigate } from 'react-router';
import Alert from '../../components/common/Alert';
import Badge from '../../components/common/Badge';
import Button from '../../components/common/Button';
import Card from '../../components/common/Card';
import FormField from '../../components/common/FormField';
import Input from '../../components/common/Input';
import ProgressSteps from '../../components/common/ProgressSteps';
import Select from '../../components/common/Select';
import Spinner from '../../components/common/Spinner';
import Textarea from '../../components/common/Textarea';
import { profileErrorMessage } from '../../features/profiles/errors';
import {
  useCompleteOnboarding,
  useMyProfile,
  useUpdateProfile,
} from '../../features/profiles/hooks';
import { profileFormSchema, type ProfileFormValues } from '../../features/profiles/schemas';
import { supportedCities } from '../../features/profiles/types';

const TOTAL_STEPS = 5;

export default function OnboardingPage() {
  const profile = useMyProfile();
  const update = useUpdateProfile();
  const complete = useCompleteOnboarding();
  const navigate = useNavigate();
  const initialized = useRef(false);
  const [step, setStep] = useState(1);
  const [completionFlowActive, setCompletionFlowActive] = useState(false);
  const form = useForm<ProfileFormValues>({
    resolver: zodResolver(profileFormSchema),
    defaultValues: { displayName: '', bio: '', city: undefined },
  });

  useEffect(() => {
    if (!profile.data || initialized.current) return;
    form.reset({
      displayName: profile.data.displayName ?? '',
      bio: profile.data.bio ?? '',
      city: profile.data.city ?? undefined,
    });
    setStep(profile.data.city && profile.data.displayName ? 4 : profile.data.displayName ? 3 : 1);
    initialized.current = true;
  }, [form, profile.data]);

  if (profile.isPending) return <Spinner label="Preparing your profile" />;
  if (profile.isError) {
    return <Alert>{profileErrorMessage(profile.error)}</Alert>;
  }
  if (profile.data?.onboardingCompleted && !completionFlowActive) {
    return <Navigate to="/profile" replace />;
  }

  async function nextFromProfile() {
    if (!(await form.trigger(['displayName', 'bio']))) return;
    const values = form.getValues();
    try {
      await update.mutateAsync({ displayName: values.displayName, bio: values.bio || null });
      setStep(3);
    } catch {
      // The safe shared error is rendered below.
    }
  }

  async function nextFromCity() {
    if (!(await form.trigger('city'))) return;
    try {
      await update.mutateAsync({ city: form.getValues('city') });
      setStep(4);
    } catch {
      // The safe shared error is rendered below.
    }
  }

  async function finish() {
    setCompletionFlowActive(true);
    try {
      await complete.mutateAsync();
      setStep(5);
    } catch {
      setCompletionFlowActive(false);
      // The safe shared error is rendered below.
    }
  }

  const error = update.error ?? complete.error;
  return (
    <div className="mx-auto max-w-2xl">
      <ProgressSteps current={step} total={TOTAL_STEPS} />
      <Card className="mt-6 overflow-hidden">
        <div className="border-b border-slate-100 bg-gradient-to-r from-red-50 to-amber-50 px-6 py-5 sm:px-8">
          <p className="text-xs font-black uppercase tracking-[0.2em] text-red-600">Profile setup</p>
          <h1 className="mt-2 text-2xl font-black tracking-tight sm:text-3xl">
            {step === 1 && 'Welcome to UniShop China'}
            {step === 2 && 'Tell the community about you'}
            {step === 3 && 'Choose your city'}
            {step === 4 && 'Review your profile status'}
            {step === 5 && 'You are ready'}
          </h1>
        </div>
        <div className="space-y-6 p-6 sm:p-8">
          {error && <Alert>{profileErrorMessage(error)}</Alert>}
          {step === 1 && (
            <>
              <p className="leading-7 text-slate-600">Create a trustworthy profile for buying and selling within international communities across China.</p>
              <Button className="w-full sm:w-auto" onClick={() => setStep(2)}>Get started</Button>
            </>
          )}
          {step === 2 && (
            <>
              <FormField id="display-name" label="Display name" error={form.formState.errors.displayName?.message}>
                <Input id="display-name" autoComplete="nickname" {...form.register('displayName')} />
              </FormField>
              <FormField id="bio" label="Bio (optional)" error={form.formState.errors.bio?.message} hint="Up to 300 characters. Plain text only.">
                <Textarea id="bio" rows={5} {...form.register('bio')} />
              </FormField>
              <div className="flex justify-between gap-3">
                <Button variant="secondary" onClick={() => setStep(1)}>Back</Button>
                <Button disabled={update.isPending} onClick={() => void nextFromProfile()}>{update.isPending ? 'Saving…' : 'Save and continue'}</Button>
              </div>
            </>
          )}
          {step === 3 && (
            <>
              <p className="text-sm leading-6 text-slate-600">Your city helps people understand where marketplace exchanges can happen. A broader city system will arrive in a later phase.</p>
              <FormField id="city" label="Current city" error={form.formState.errors.city?.message}>
                <Select id="city" {...form.register('city')}>
                  <option value="">Choose your city</option>
                  {supportedCities.map((city) => <option key={city} value={city}>{city}</option>)}
                </Select>
              </FormField>
              <div className="flex justify-between gap-3">
                <Button variant="secondary" onClick={() => setStep(2)}>Back</Button>
                <Button disabled={update.isPending} onClick={() => void nextFromCity()}>{update.isPending ? 'Saving…' : 'Save and continue'}</Button>
              </div>
            </>
          )}
          {step === 4 && profile.data && (
            <>
              <dl className="grid gap-4 rounded-xl bg-slate-50 p-5 sm:grid-cols-2">
                <div><dt className="text-xs font-bold uppercase text-slate-500">Display name</dt><dd className="mt-1 font-semibold">{form.getValues('displayName')}</dd></div>
                <div><dt className="text-xs font-bold uppercase text-slate-500">City</dt><dd className="mt-1 font-semibold">{form.getValues('city')}</dd></div>
              </dl>
              <div className="flex flex-wrap gap-2">
                <Badge positive={profile.data.emailVerified}>Email {profile.data.emailVerified ? 'verified' : 'not verified'}</Badge>
                <Badge positive={profile.data.phoneVerified}>Phone {profile.data.phoneVerified ? 'verified' : 'not verified'}</Badge>
                <Badge>Profile awaiting completion</Badge>
              </div>
              <div className="flex justify-between gap-3">
                <Button variant="secondary" onClick={() => setStep(3)}>Back</Button>
                <Button disabled={complete.isPending} onClick={() => void finish()}>{complete.isPending ? 'Finishing…' : 'Finish setup'}</Button>
              </div>
            </>
          )}
          {step === 5 && (
            <div className="text-center">
              <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-emerald-100 text-2xl text-emerald-700" aria-hidden="true">✓</div>
              <p className="mt-4 leading-7 text-slate-600">Your profile is complete and ready for the UniShop community.</p>
              <Button className="mt-6" onClick={() => navigate('/profile', { replace: true })}>View my profile</Button>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
