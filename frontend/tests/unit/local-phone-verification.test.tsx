import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  SafeLocalApiError,
  type FakeSmsMessage,
  type LocalFakeSmsApi,
} from '../../src/features/auth/localFakeSmsApi';
import { LocalPhoneVerificationPage } from '../../src/pages/dev/LocalPhoneVerificationPage';

function testPhone(): string {
  return `+86138${String(Math.floor(Math.random() * 100_000_000)).padStart(8, '0')}`;
}

function deliveredMessage(
  deliveryType: FakeSmsMessage['deliveryType'] = 'registration',
): FakeSmsMessage {
  return {
    messageId: crypto.randomUUID(),
    phoneNumberMasked: '+86138****1234',
    code: '483921',
    deliveryType,
    createdAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 600_000).toISOString(),
    expiresInSeconds: 600,
  };
}

function createApi(overrides: Partial<LocalFakeSmsApi> = {}): LocalFakeSmsApi {
  return {
    register: vi.fn().mockResolvedValue(undefined),
    resend: vi.fn().mockResolvedValue(undefined),
    latest: vi.fn().mockResolvedValue(deliveredMessage()),
    verify: vi.fn().mockResolvedValue({ phoneVerified: true }),
    consume: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

async function fillPhone(user: ReturnType<typeof userEvent.setup>, phone: string) {
  await user.type(screen.getByLabelText('Chinese phone number'), phone);
}

async function fillRegistration(
  user: ReturnType<typeof userEvent.setup>,
  phone: string,
  password = 'StrongPass9',
) {
  await fillPhone(user, phone);
  await user.type(screen.getByLabelText('Password'), password);
}

afterEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

describe('LocalPhoneVerificationPage', () => {
  it('clearly labels the tool as local-only and uses safe input attributes', () => {
    render(<LocalPhoneVerificationPage api={createApi()} />);

    expect(screen.getByText('Development Fake SMS')).toBeInTheDocument();
    expect(screen.getByText('No real SMS will be sent to the phone.')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
    expect(screen.getByLabelText('Password')).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByLabelText('Six-digit OTP')).toHaveAttribute('maxlength', '6');
  });

  it('registers, clears the password, polls, and displays only the masked phone', async () => {
    const user = userEvent.setup();
    const phone = testPhone();
    const message = deliveredMessage();
    const api = createApi({ latest: vi.fn().mockResolvedValue(message) });
    render(<LocalPhoneVerificationPage api={api} pollIntervalMs={1} />);

    await fillRegistration(user, phone);
    await user.click(screen.getByRole('button', { name: 'Register test account' }));

    await screen.findByText(message.code);
    expect(api.register).toHaveBeenCalledWith(phone, 'StrongPass9');
    expect(screen.getByLabelText('Password')).toHaveValue('');
    expect(screen.getByText(`Masked phone: ${message.phoneNumberMasked}`)).toBeInTheDocument();
    expect(screen.queryByText(phone)).not.toBeInTheDocument();
    expect(localStorage).toHaveLength(0);
    expect(sessionStorage).toHaveLength(0);
  });

  it('accepts manual OTP entry, consumes the displayed message, and clears the OTP', async () => {
    const user = userEvent.setup();
    const phone = testPhone();
    const message = deliveredMessage();
    const api = createApi({ latest: vi.fn().mockResolvedValue(message) });
    render(<LocalPhoneVerificationPage api={api} pollIntervalMs={1} />);

    await fillRegistration(user, phone);
    await user.click(screen.getByRole('button', { name: 'Register test account' }));
    await screen.findByText(message.code);
    await user.type(screen.getByLabelText('Six-digit OTP'), message.code);
    await user.click(screen.getByRole('button', { name: 'Verify phone' }));

    await screen.findByText('phone_verified=true');
    expect(api.verify).toHaveBeenCalledWith(phone, message.code);
    expect(api.consume).toHaveBeenCalledWith(message.messageId);
    expect(screen.getByLabelText('Six-digit OTP')).toHaveValue('');
    expect(screen.queryByText(message.code)).not.toBeInTheDocument();
  });

  it('prevents duplicate registration requests while one is pending', async () => {
    const user = userEvent.setup();
    let resolveRegistration: (() => void) | undefined;
    const register = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveRegistration = resolve;
        }),
    );
    const api = createApi({ register });
    render(<LocalPhoneVerificationPage api={api} />);

    await fillRegistration(user, testPhone());
    const button = screen.getByRole('button', { name: 'Register test account' });
    await user.click(button);
    await user.click(button);

    expect(register).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();
    resolveRegistration?.();
    await waitFor(() => expect(button).not.toBeDisabled());
  });

  it('shows a safe error without exposing backend details', async () => {
    const user = userEvent.setup();
    const api = createApi({
      register: vi.fn().mockRejectedValue(new SafeLocalApiError('This account already exists.')),
    });
    render(<LocalPhoneVerificationPage api={api} />);

    await fillRegistration(user, testPhone());
    await user.click(screen.getByRole('button', { name: 'Register test account' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('This account already exists.');
    expect(screen.getByRole('alert')).not.toHaveTextContent('SQL');
    expect(screen.getByLabelText('Password')).toHaveValue('');
  });

  it('keeps the delivered message available after a wrong verification code', async () => {
    const user = userEvent.setup();
    const phone = testPhone();
    const message = deliveredMessage();
    const api = createApi({
      latest: vi.fn().mockResolvedValue(message),
      verify: vi
        .fn()
        .mockRejectedValue(new SafeLocalApiError('The verification code is incorrect.')),
    });
    render(<LocalPhoneVerificationPage api={api} pollIntervalMs={1} />);

    await fillRegistration(user, phone);
    await user.click(screen.getByRole('button', { name: 'Register test account' }));
    await screen.findByText(message.code);
    await user.type(screen.getByLabelText('Six-digit OTP'), '000000');
    await user.click(screen.getByRole('button', { name: 'Verify phone' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The verification code is incorrect.',
    );
    expect(screen.getByText(message.code)).toBeInTheDocument();
    expect(api.consume).not.toHaveBeenCalled();
  });

  it('requests a resend and displays the replacement message', async () => {
    const user = userEvent.setup();
    const phone = testPhone();
    const message = deliveredMessage('resend');
    const api = createApi({ latest: vi.fn().mockResolvedValue(message) });
    render(<LocalPhoneVerificationPage api={api} pollIntervalMs={1} />);

    await fillPhone(user, phone);
    await user.click(screen.getByRole('button', { name: 'Request new code' }));

    await screen.findByText(message.code);
    expect(api.resend).toHaveBeenCalledWith(phone);
    expect(screen.getByText('Message type: resend')).toBeInTheDocument();
  });

  it('stops bounded polling and reports a safe timeout', async () => {
    const user = userEvent.setup();
    const api = createApi({ latest: vi.fn().mockResolvedValue(null) });
    render(
      <LocalPhoneVerificationPage api={api} pollIntervalMs={1} pollTimeoutMs={5} />,
    );

    await fillRegistration(user, testPhone());
    await user.click(screen.getByRole('button', { name: 'Register test account' }));

    expect(
      await screen.findByText('No fake message delivered within 1 seconds'),
    ).toBeInTheDocument();
    expect(api.latest).toHaveBeenCalled();
  });

  it('aborts an outstanding inbox request when unmounted', async () => {
    const user = userEvent.setup();
    let observedSignal: AbortSignal | undefined;
    const api = createApi({
      latest: vi.fn((_phone, signal) => {
        observedSignal = signal;
        return new Promise<FakeSmsMessage | null>(() => undefined);
      }),
    });
    const view = render(<LocalPhoneVerificationPage api={api} />);

    await fillRegistration(user, testPhone());
    await user.click(screen.getByRole('button', { name: 'Register test account' }));
    await waitFor(() => expect(observedSignal).toBeDefined());
    view.unmount();

    expect(observedSignal?.aborted).toBe(true);
  });
});
