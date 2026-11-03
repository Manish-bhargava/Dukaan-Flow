import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { loginWithPassword, sendOtp, verifyOtp, type TokenData } from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Logo } from '../components/Logo'
import { ProductArt } from '../components/ProductArt'
import { Spinner } from '../components/Spinner'
import { Link } from '../components/Link'
import { navigate } from '../router'

const PHONE_PATTERN = /^[6-9]\d{9}$/

type Mode = 'retailer' | 'staff'
type Alert = { tone: 'error' | 'info' | 'success'; text: string } | null

export function LoginPage() {
  const { state, signIn } = useAuth()
  const [mode, setMode] = useState<Mode>(() => (new URLSearchParams(window.location.search).has('staff') ? 'staff' : 'retailer'))
  const notice = state.status === 'anonymous' ? state.notice : undefined

  const onSignedIn = (data: TokenData) => {
    signIn(data)
    navigate('/home', { replace: true })
  }

  return (
    <div className="grid min-h-screen bg-cream-50 lg:grid-cols-[1fr_1.1fr]">
      <BrandPanel />
      <div className="flex flex-col px-5 py-6 sm:px-10">
        <div className="flex items-center justify-between lg:justify-end">
          <span className="lg:hidden">
            <Logo />
          </span>
          <Link to="/" className="rounded-full px-4 py-2 text-sm font-semibold text-ink-soft hover:bg-leaf-50 hover:text-leaf-700">
            ← Back to home
          </Link>
        </div>

        <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center py-10">
          <h1 className="text-3xl font-extrabold tracking-tight text-leaf-900">Welcome to DukaanFlow</h1>
          <p className="mt-2 text-ink-soft">Log in with the mobile number registered with your distributor.</p>

          <div className="mt-8 grid grid-cols-2 rounded-full bg-cream-100 p-1 ring-1 ring-cream-200" role="tablist" aria-label="Login type">
            {(['retailer', 'staff'] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={mode === m}
                onClick={() => setMode(m)}
                className={`rounded-full py-2.5 text-sm font-bold transition ${
                  mode === m ? 'bg-leaf-700 text-cream-50 shadow-sm' : 'text-ink-soft hover:text-leaf-700'
                }`}
              >
                {m === 'retailer' ? 'Retailer' : 'Staff'}
              </button>
            ))}
          </div>

          {notice && <AlertBox alert={{ tone: 'info', text: notice }} />}

          <div className="mt-6 rounded-3xl bg-white p-6 shadow-sm ring-1 ring-cream-200 sm:p-8">
            {mode === 'retailer' ? <RetailerOtpLogin onSignedIn={onSignedIn} /> : <StaffLogin onSignedIn={onSignedIn} />}
          </div>
        </div>
      </div>
    </div>
  )
}

function RetailerOtpLogin({ onSignedIn }: { onSignedIn: (data: TokenData) => void }) {
  const [step, setStep] = useState<'phone' | 'otp'>('phone')
  const [phone, setPhone] = useState('')
  const [otp, setOtp] = useState('')
  const [busy, setBusy] = useState(false)
  const [alert, setAlert] = useState<Alert>(null)
  const [expiresAt, setExpiresAt] = useState(0)
  const [resendAt, setResendAt] = useState(0)
  const [used, setUsed] = useState(false) // OTP invalidated by the server (expired / too many attempts)
  const now = useNow()
  const otpInput = useRef<HTMLInputElement>(null)

  const secondsLeft = Math.max(0, Math.ceil((expiresAt - now) / 1000))
  const resendIn = Math.max(0, Math.ceil((resendAt - now) / 1000))
  const expired = step === 'otp' && (used || secondsLeft === 0)

  async function requestOtp() {
    if (!PHONE_PATTERN.test(phone)) {
      setAlert({ tone: 'error', text: 'Enter a valid 10-digit mobile number.' })
      return
    }
    setBusy(true)
    setAlert(null)
    try {
      const res = await sendOtp(phone)
      const sentAt = Date.now()
      setExpiresAt(sentAt + res.data.expires_in * 1000)
      setResendAt(sentAt + res.data.resend_after * 1000)
      setUsed(false)
      setOtp('')
      setStep('otp')
      setAlert({ tone: 'success', text: res.message })
      window.setTimeout(() => otpInput.current?.focus(), 50)
    } catch (err) {
      if (err instanceof ApiError && err.details.reason === 'RESEND_COOLDOWN') {
        setResendAt(Date.now() + Number(err.details.retry_after ?? 0) * 1000)
      }
      setAlert({ tone: 'error', text: messageOf(err) })
    } finally {
      setBusy(false)
    }
  }

  async function submitOtp(code = otp) {
    if (!/^\d{6}$/.test(code) || busy || expired) return
    setBusy(true)
    setAlert(null)
    try {
      onSignedIn((await verifyOtp(phone, code)).data)
    } catch (err) {
      setOtp('')
      if (err instanceof ApiError && err.code === 'INVALID_OTP') {
        const left = Number(err.details.remaining_attempts)
        setAlert({ tone: 'error', text: `Incorrect OTP. ${left} attempt${left === 1 ? '' : 's'} left.` })
        otpInput.current?.focus()
      } else if (err instanceof ApiError && (err.code === 'OTP_EXPIRED' || err.code === 'OTP_ATTEMPTS_EXCEEDED')) {
        setUsed(true)
        setAlert({ tone: 'error', text: err.message })
      } else {
        setAlert({ tone: 'error', text: messageOf(err) })
      }
      setBusy(false)
    }
  }

  if (step === 'phone') {
    return (
      <form
        noValidate
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          void requestOtp()
        }}
      >
        <PhoneField value={phone} onChange={setPhone} autoFocus />
        <p className="mt-3 text-sm text-ink-soft">We’ll email a 6-digit code to the email address registered on your account.</p>
        <AlertBox alert={alert} />
        <SubmitButton busy={busy}>Send OTP</SubmitButton>
      </form>
    )
  }

  return (
    <form
      noValidate
      onSubmit={(e: FormEvent) => {
        e.preventDefault()
        void submitOtp()
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-ink-soft">Code sent for</p>
          <p className="text-lg font-bold text-leaf-900">+91 {phone.slice(0, 5)} {phone.slice(5)}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setStep('phone')
            setAlert(null)
          }}
          className="rounded-full px-3 py-1.5 text-sm font-bold text-leaf-700 hover:bg-leaf-50"
        >
          Change number
        </button>
      </div>

      <label htmlFor="otp" className="mt-6 block text-sm font-bold text-leaf-900">
        Enter the 6-digit OTP from your email
      </label>
      <input
        ref={otpInput}
        id="otp"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        value={otp}
        disabled={busy || expired}
        onChange={(e) => {
          const code = e.target.value.replace(/\D/g, '').slice(0, 6)
          setOtp(code)
          if (code.length === 6) void submitOtp(code)
        }}
        placeholder="••••••"
        className="mt-2 w-full rounded-2xl border-0 bg-cream-50 px-4 py-4 text-center text-2xl font-extrabold tracking-[0.6em] text-leaf-900 ring-1 ring-cream-300 outline-none transition placeholder:text-cream-300 focus:ring-2 focus:ring-leaf-500 disabled:opacity-60"
      />

      <div className="mt-3 flex items-center justify-between text-sm">
        <span className={expired ? 'font-semibold text-red-700' : 'text-ink-soft'}>
          {expired ? 'This code is no longer valid' : `Code expires in ${formatSeconds(secondsLeft)}`}
        </span>
        <button
          type="button"
          disabled={busy || resendIn > 0}
          onClick={() => void requestOtp()}
          className="font-bold text-leaf-700 hover:underline disabled:cursor-not-allowed disabled:text-ink-soft/60 disabled:no-underline"
        >
          {resendIn > 0 ? `Resend in ${resendIn}s` : 'Resend OTP'}
        </button>
      </div>

      <AlertBox alert={alert} />
      <SubmitButton busy={busy} disabled={otp.length !== 6 || expired}>
        Verify & log in
      </SubmitButton>
      <p className="mt-4 text-center text-xs text-ink-soft">Didn’t get it? Check your spam folder. A new code replaces the old one.</p>
    </form>
  )
}

function StaffLogin({ onSignedIn }: { onSignedIn: (data: TokenData) => void }) {
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [alert, setAlert] = useState<Alert>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!PHONE_PATTERN.test(phone) || !password) {
      setAlert({ tone: 'error', text: 'Enter your 10-digit mobile number and password.' })
      return
    }
    setBusy(true)
    setAlert(null)
    try {
      onSignedIn((await loginWithPassword(phone, password)).data)
    } catch (err) {
      setAlert({ tone: 'error', text: messageOf(err) })
      setBusy(false)
    }
  }

  return (
    <form noValidate onSubmit={submit}>
      <p className="mb-5 text-sm text-ink-soft">For salesmen, order desk and admin accounts.</p>
      <PhoneField value={phone} onChange={setPhone} autoFocus />
      <label htmlFor="password" className="mt-5 block text-sm font-bold text-leaf-900">
        Password
      </label>
      <input
        id="password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="mt-2 w-full rounded-2xl border-0 bg-cream-50 px-4 py-3.5 text-leaf-900 ring-1 ring-cream-300 outline-none transition focus:ring-2 focus:ring-leaf-500"
      />
      <AlertBox alert={alert} />
      <SubmitButton busy={busy}>Log in</SubmitButton>
    </form>
  )
}

function PhoneField({ value, onChange, autoFocus }: { value: string; onChange: (v: string) => void; autoFocus?: boolean }) {
  return (
    <>
      <label htmlFor="phone" className="block text-sm font-bold text-leaf-900">
        Mobile number
      </label>
      <div className="mt-2 flex rounded-2xl bg-cream-50 ring-1 ring-cream-300 transition focus-within:ring-2 focus-within:ring-leaf-500">
        <span className="flex items-center border-r border-cream-300 px-4 font-bold text-ink-soft">+91</span>
        <input
          id="phone"
          type="tel"
          inputMode="numeric"
          autoComplete="tel-national"
          autoFocus={autoFocus}
          maxLength={10}
          placeholder="98765 43210"
          value={value}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, '').slice(0, 10))}
          className="w-full rounded-r-2xl border-0 bg-transparent px-4 py-3.5 text-lg font-semibold tracking-wide text-leaf-900 outline-none placeholder:font-normal placeholder:text-ink-soft/40"
        />
      </div>
    </>
  )
}

function SubmitButton({ busy, disabled, children }: { busy: boolean; disabled?: boolean; children: ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy || disabled}
      className="mt-6 flex w-full items-center justify-center gap-2 rounded-full bg-leaf-700 py-4 font-bold text-cream-50 shadow-md shadow-leaf-900/15 transition hover:bg-leaf-800 disabled:cursor-not-allowed disabled:bg-leaf-700/50 disabled:shadow-none"
    >
      {busy && <Spinner />}
      {busy ? 'Please wait…' : children}
    </button>
  )
}

function AlertBox({ alert }: { alert: Alert }) {
  if (!alert) return null
  const styles = {
    error: 'bg-red-50 text-red-800 ring-red-200',
    info: 'bg-mango-100 text-leaf-950 ring-mango-200',
    success: 'bg-leaf-50 text-leaf-800 ring-leaf-200',
  }[alert.tone]
  return (
    <p role={alert.tone === 'error' ? 'alert' : 'status'} className={`mt-4 rounded-2xl px-4 py-3 text-sm font-medium ring-1 ${styles}`}>
      {alert.text}
    </p>
  )
}

function BrandPanel() {
  return (
    <aside className="relative hidden overflow-hidden bg-leaf-800 p-12 lg:flex lg:flex-col lg:justify-between">
      <div className="absolute inset-x-0 top-0 flex h-8">
        {Array.from({ length: 14 }, (_, i) => (
          <div key={i} className={`flex-1 ${i % 2 ? 'bg-cream-50' : 'bg-mango-400'}`} />
        ))}
      </div>
      <div className="pointer-events-none absolute -bottom-24 -right-24 h-96 w-96 rounded-full bg-mango-400/15 blur-3xl" />
      <div className="mt-8">
        <Logo light />
      </div>
      <div className="relative">
        <div className="flex gap-4">
          {(['biscuits', 'tea', 'homecare'] as const).map((kind, i) => (
            <div key={kind} className="animate-float rounded-3xl bg-cream-100 p-3" style={{ animationDelay: `${i * 0.6}s` }}>
              <ProductArt kind={kind} className="h-20 w-20" />
            </div>
          ))}
        </div>
        <h2 className="mt-10 max-w-md text-4xl font-extrabold leading-tight text-cream-50">
          Your distributor’s full catalogue, <span className="text-mango-300">at your price.</span>
        </h2>
        <p className="mt-4 max-w-md text-lg text-leaf-100">Order any time, see schemes before you buy, and track every order to your shop.</p>
      </div>
      <p className="relative text-sm text-leaf-200/70">Secure login: one-time codes expire in 2 minutes.</p>
    </aside>
  )
}

function useNow(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  return now
}

function formatSeconds(total: number): string {
  const m = Math.floor(total / 60)
  const s = total % 60
  return m ? `${m}:${String(s).padStart(2, '0')}` : `${s}s`
}

function messageOf(err: unknown): string {
  if (err instanceof ApiError && err.code === 'RATE_LIMIT_EXCEEDED') {
    const wait = Number(err.details.retry_after ?? 0)
    return wait ? `${err.message} Try again in ${formatSeconds(wait)}.` : err.message
  }
  return err instanceof Error ? err.message : 'Something went wrong. Please try again.'
}
