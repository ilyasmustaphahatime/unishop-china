import { useCallback, useEffect, useRef, useState } from 'react';
import {
  localFakeSmsApi,
  SafeLocalApiError,
  type FakeSmsMessage,
  type LocalFakeSmsApi,
} from '../../features/auth/localFakeSmsApi';

type Props = {
  api?: LocalFakeSmsApi;
  pollIntervalMs?: number;
  pollTimeoutMs?: number;
};

function normalizePhone(value: string): string | null {
  let candidate = value.replace(/[\s()-]/g, '');
  if (candidate.startsWith('+86')) candidate = candidate.slice(3);
  if (candidate.startsWith('0086')) candidate = candidate.slice(4);
  return /^1[3-9][0-9]{9}$/.test(candidate) ? `+86${candidate}` : null;
}

function validatePassword(value: string): string | null {
  if (value.length < 8 || value.length > 128) {
    return 'Password must contain between 8 and 128 characters.';
  }
  if (!/[A-Z]/.test(value) || !/[a-z]/.test(value) || !/[0-9]/.test(value)) {
    return 'Password must contain uppercase, lowercase, and numeric characters.';
  }
  return null;
}

function userMessage(error: unknown): string {
  return error instanceof SafeLocalApiError
    ? error.userMessage
    : 'The request could not be completed.';
}

export function LocalPhoneVerificationPage({
  api = localFakeSmsApi,
  pollIntervalMs = 1_000,
  pollTimeoutMs = 20_000,
}: Props) {
  const [phoneInput, setPhoneInput] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [message, setMessage] = useState<FakeSmsMessage | null>(null);
  const [deliveryStatus, setDeliveryStatus] = useState('Idle');
  const [error, setError] = useState('');
  const [pendingAction, setPendingAction] = useState<'register' | 'resend' | 'verify' | null>(
    null,
  );
  const [verified, setVerified] = useState(false);
  const [pollRequest, setPollRequest] = useState<{ phone: string; sequence: number } | null>(
    null,
  );
  const [expiresIn, setExpiresIn] = useState(0);
  const sequence = useRef(0);

  const startPolling = useCallback((phone: string) => {
    sequence.current += 1;
    setMessage(null);
    setExpiresIn(0);
    setDeliveryStatus('Waiting for simulated delivery…');
    setPollRequest({ phone, sequence: sequence.current });
  }, []);

  useEffect(() => {
    if (!pollRequest || verified) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;
    const deadline = Date.now() + pollTimeoutMs;

    const poll = async () => {
      controller = new AbortController();
      try {
        const delivered = await api.latest(pollRequest.phone, controller.signal);
        if (!active) return;
        if (delivered) {
          setMessage(delivered);
          setExpiresIn(delivered.expiresInSeconds);
          setDeliveryStatus('Delivered to the local fake inbox');
          setPollRequest(null);
          return;
        }
      } catch (pollError) {
        if (!active) return;
        setError(userMessage(pollError));
        setDeliveryStatus('Delivery check stopped');
        setPollRequest(null);
        return;
      }
      if (Date.now() >= deadline) {
        setDeliveryStatus(
          `No fake message delivered within ${Math.ceil(pollTimeoutMs / 1_000)} seconds`,
        );
        setPollRequest(null);
        return;
      }
      timer = setTimeout(poll, pollIntervalMs);
    };

    void poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
      controller?.abort();
    };
  }, [api, pollIntervalMs, pollRequest, pollTimeoutMs, verified]);

  useEffect(() => {
    if (!message) return;
    const timer = setInterval(() => {
      setExpiresIn((value) => Math.max(0, value - 1));
    }, 1_000);
    return () => clearInterval(timer);
  }, [message]);

  const validatedPhone = () => {
    const normalized = normalizePhone(phoneInput);
    if (!normalized) setError('Enter a valid mainland Chinese mobile number.');
    return normalized;
  };

  const register = async () => {
    if (pendingAction) return;
    const phone = validatedPhone();
    const passwordError = validatePassword(password);
    if (!phone || passwordError) {
      if (passwordError) setError(passwordError);
      return;
    }
    setPendingAction('register');
    setError('');
    setVerified(false);
    try {
      await api.register(phone, password);
      startPolling(phone);
    } catch (requestError) {
      setError(userMessage(requestError));
    } finally {
      setPassword('');
      setPendingAction(null);
    }
  };

  const resend = async () => {
    if (pendingAction) return;
    const phone = validatedPhone();
    if (!phone) return;
    setPendingAction('resend');
    setError('');
    setVerified(false);
    try {
      await api.resend(phone);
      startPolling(phone);
    } catch (requestError) {
      setError(userMessage(requestError));
    } finally {
      setPendingAction(null);
    }
  };

  const verify = async () => {
    if (pendingAction) return;
    const phone = validatedPhone();
    if (!phone) return;
    if (!/^[0-9]{6}$/.test(otp)) {
      setError('Enter the six-digit verification code.');
      return;
    }
    setPendingAction('verify');
    setError('');
    try {
      const result = await api.verify(phone, otp);
      if (result.phoneVerified) {
        const messageId = message?.messageId;
        setVerified(true);
        setDeliveryStatus('Phone verified');
        setOtp('');
        setMessage(null);
        setPollRequest(null);
        if (messageId) await api.consume(messageId);
      }
    } catch (requestError) {
      setError(userMessage(requestError));
    } finally {
      setPendingAction(null);
    }
  };

  const copyCode = async () => {
    if (message) await navigator.clipboard.writeText(message.code);
  };

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-amber-700">
          Development Fake SMS
        </p>
        <h1 className="text-3xl font-bold text-slate-900">Local Phone Verification Test</h1>
        <p className="mt-2 rounded-lg bg-amber-50 p-3 text-amber-900">
          No real SMS will be sent to the phone.
        </p>
      </header>

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 p-3 text-red-800">
          {error}
        </div>
      )}
      {verified && (
        <div role="status" className="rounded-lg bg-green-50 p-3 text-green-800">
          phone_verified=true
        </div>
      )}

      <section className="rounded-xl border border-slate-200 p-5">
        <h2 className="text-xl font-semibold">Registration</h2>
        <label className="mt-4 block">
          <span>Chinese phone number</span>
          <input
            aria-label="Chinese phone number"
            value={phoneInput}
            onChange={(event) => setPhoneInput(event.target.value)}
            className="mt-1 block w-full rounded border p-2"
            autoComplete="tel"
          />
        </label>
        <label className="mt-4 block">
          <span>Password</span>
          <input
            aria-label="Password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 block w-full rounded border p-2"
            autoComplete="new-password"
          />
        </label>
        <div className="mt-4 flex gap-3">
          <button
            type="button"
            disabled={pendingAction !== null}
            onClick={() => void register()}
            className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-50"
          >
            Register test account
          </button>
          <button
            type="button"
            disabled={pendingAction !== null}
            onClick={() => void resend()}
            className="rounded border px-4 py-2 disabled:opacity-50"
          >
            Request new code
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 p-5">
        <h2 className="text-xl font-semibold">Fake SMS inbox</h2>
        <p className="mt-2" role="status">
          {deliveryStatus}
        </p>
        {message && (
          <div className="mt-4 space-y-2 rounded-lg bg-slate-50 p-4">
            <p>Masked phone: {message.phoneNumberMasked}</p>
            <p>Message type: {message.deliveryType}</p>
            <p className="font-mono text-2xl tracking-widest">{message.code}</p>
            <p>Expires in: {expiresIn} seconds</p>
            <button
              type="button"
              onClick={() => void copyCode()}
              className="rounded border px-3 py-1"
            >
              Copy code
            </button>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 p-5">
        <h2 className="text-xl font-semibold">Verification</h2>
        <label className="mt-4 block">
          <span>Six-digit OTP</span>
          <input
            aria-label="Six-digit OTP"
            value={otp}
            onChange={(event) => setOtp(event.target.value.replace(/[^0-9]/g, '').slice(0, 6))}
            className="mt-1 block w-full rounded border p-2 font-mono"
            inputMode="numeric"
            maxLength={6}
            autoComplete="one-time-code"
          />
        </label>
        <button
          type="button"
          disabled={pendingAction !== null || verified}
          onClick={() => void verify()}
          className="mt-4 rounded bg-green-700 px-4 py-2 text-white disabled:opacity-50"
        >
          Verify phone
        </button>
      </section>
    </main>
  );
}

export default LocalPhoneVerificationPage;
