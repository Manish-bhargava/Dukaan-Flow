import { useEffect, useState, type ReactNode } from 'react'
import { Logo } from '../components/Logo'
import { ProductArt } from '../components/ProductArt'
import type { ArtKind } from '../components/productKinds'
import { useReveal } from '../components/useReveal'
import { Link } from '../components/Link'

const YEAR = new Date().getFullYear()

const NAV = [
  { href: '#home', label: 'Home' },
  { href: '#features', label: 'Features' },
  { href: '#about', label: 'About' },
  { href: '#support', label: 'Support' },
]

const CATEGORIES: { kind: ArtKind; name: string; note: string; tint: string }[] = [
  { kind: 'biscuits', name: 'Biscuits', note: 'Glucose, cream & cookies', tint: 'bg-mango-100' },
  { kind: 'snacks', name: 'Snacks', note: 'Namkeen & chips', tint: 'bg-leaf-50' },
  { kind: 'tea', name: 'Tea', note: 'Leaf & dust packs', tint: 'bg-cream-200' },
  { kind: 'beverages', name: 'Beverages', note: 'Soft drinks & juices', tint: 'bg-mango-100' },
  { kind: 'noodles', name: 'Noodles', note: 'Instant & pasta', tint: 'bg-leaf-50' },
  { kind: 'staples', name: 'Staples', note: 'Atta, rice & dal', tint: 'bg-cream-200' },
  { kind: 'homecare', name: 'Home Care', note: 'Detergent & dishwash', tint: 'bg-mango-100' },
  { kind: 'personal', name: 'Personal Care', note: 'Soap, shampoo & more', tint: 'bg-leaf-50' },
]

const BENEFITS = [
  {
    title: 'Easy ordering',
    text: 'Add cases from the catalogue, or just type your order the way you would say it: “5 peti biscuit, 2 peti chai patti”.',
    icon: 'M3 4h2l2.4 10.2a2 2 0 0 0 2 1.6h7.8a2 2 0 0 0 1.9-1.4L21 8H6.2M9 20h.01M17 20h.01',
  },
  {
    title: 'Product discovery',
    text: 'Browse every category your distributor stocks, search by name or brand, and spot active schemes at a glance.',
    icon: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm10 2-4.35-4.35',
  },
  {
    title: 'Order tracking',
    text: 'See each order move from placed to approved and dispatched. No more calling the office to ask about status.',
    icon: 'M9 12l2 2 4-4M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20Z',
  },
  {
    title: 'Reliable supply',
    text: 'Live stock from the distributor’s warehouse, your own dealer prices and credit, checked before an order is approved.',
    icon: 'M3 7l9-4 9 4-9 4-9-4Zm0 0v10l9 4 9-4V7M12 11v10',
  },
]

const STEPS = [
  { title: 'Log in with your mobile', text: 'Enter your registered number. A one-time code is sent to your registered email.' },
  { title: 'Pick or type your order', text: 'Browse at your own prices, or type your order in Hindi or English. Schemes apply automatically.' },
  { title: 'We approve and dispatch', text: 'The order desk checks stock and credit, approves, and your stock is on its way.' },
]

const ROLES = [
  { title: 'Kirana retailers', text: 'Order any time of day, see your dealer prices and outstanding credit, and reorder in a few taps.' },
  { title: 'Salesmen', text: 'Book orders for assigned shops on the route without paper slips or retyping.' },
  { title: 'Order desk & owners', text: 'One queue to review, correct and approve orders, with stock and credit limits enforced.' },
]

export function LandingPage() {
  return (
    <div className="min-h-screen overflow-x-clip bg-cream-50">
      <Navbar />
      <main>
        <Hero />
        <Categories />
        <Features />
        <HowItWorks />
        <About />
        <CallToAction />
        <Support />
      </main>
      <Footer />
    </div>
  )
}

function Navbar() {
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header
      className={`sticky top-0 z-40 transition-all duration-300 ${
        scrolled || open ? 'bg-cream-50/90 shadow-[0_1px_0_rgba(23,96,54,0.08)] backdrop-blur-md' : 'bg-transparent'
      }`}
    >
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:h-20 sm:px-8" aria-label="Main">
        <Logo />
        <ul className="hidden items-center gap-1 md:flex">
          {NAV.map((item) => (
            <li key={item.href}>
              <a
                href={item.href}
                className="rounded-full px-4 py-2 text-sm font-semibold text-ink-soft transition-colors hover:bg-leaf-50 hover:text-leaf-700"
              >
                {item.label}
              </a>
            </li>
          ))}
        </ul>
        <div className="hidden items-center gap-2 md:flex">
          <Link to="/login" className="rounded-full px-5 py-2.5 text-sm font-bold text-leaf-700 transition-colors hover:bg-leaf-50">
            Login
          </Link>
          <Link
            to="/login"
            className="rounded-full bg-leaf-700 px-5 py-2.5 text-sm font-bold text-cream-50 shadow-sm shadow-leaf-900/20 transition hover:-translate-y-0.5 hover:bg-leaf-800"
          >
            Get Started
          </Link>
        </div>
        <button
          type="button"
          className="rounded-xl p-2 text-leaf-800 hover:bg-leaf-50 md:hidden"
          aria-expanded={open}
          aria-controls="mobile-menu"
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((v) => !v)}
        >
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            {open ? <path d="M6 6l12 12M18 6 6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
          </svg>
        </button>
      </nav>
      {open && (
        <div id="mobile-menu" className="border-t border-leaf-100 px-5 pb-5 md:hidden">
          <ul className="flex flex-col py-2">
            {NAV.map((item) => (
              <li key={item.href}>
                <a href={item.href} onClick={() => setOpen(false)} className="block rounded-xl px-3 py-3 font-semibold text-ink-soft hover:bg-leaf-50">
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
          <div className="grid grid-cols-2 gap-3">
            <Link to="/login" className="rounded-full border border-leaf-200 py-3 text-center font-bold text-leaf-700">
              Login
            </Link>
            <Link to="/login" className="rounded-full bg-leaf-700 py-3 text-center font-bold text-cream-50">
              Get Started
            </Link>
          </div>
        </div>
      )}
    </header>
  )
}

function Hero() {
  return (
    <section id="home" className="relative scroll-mt-24">
      <div className="pointer-events-none absolute -top-24 right-[-10%] h-[520px] w-[520px] rounded-full bg-mango-200/50 blur-3xl" />
      <div className="pointer-events-none absolute left-[-15%] top-40 h-[420px] w-[420px] rounded-full bg-leaf-100/70 blur-3xl" />

      <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-5 pb-20 pt-8 sm:px-8 lg:grid-cols-[1.05fr_1fr] lg:pb-28 lg:pt-14">
        <div className="animate-fade-up">
          <span className="inline-flex items-center gap-2 rounded-full bg-leaf-50 px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-leaf-700 ring-1 ring-leaf-100">
            <span className="h-2 w-2 rounded-full bg-mango-400" />
            B2B ordering for kirana stores
          </span>
          <h1 className="mt-6 text-4xl font-extrabold leading-[1.08] tracking-tight text-leaf-900 sm:text-5xl lg:text-6xl">
            Restock your dukaan <span className="relative whitespace-nowrap text-leaf-600">
              in minutes
              <svg viewBox="0 0 220 14" className="absolute -bottom-2 left-0 w-full" aria-hidden="true">
                <path d="M3 10c50-8 160-10 214-3" fill="none" stroke="#fbc124" strokeWidth="6" strokeLinecap="round" />
              </svg>
            </span>
            , not phone calls.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-soft">
            DukaanFlow connects kirana retailers with their FMCG distributor. Browse the catalogue at your own dealer
            price, see live schemes, place orders any time, and track them until they reach your shop.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Link
              to="/login"
              className="group inline-flex items-center justify-center gap-2 rounded-full bg-leaf-700 px-7 py-4 font-bold text-cream-50 shadow-lg shadow-leaf-900/20 transition hover:-translate-y-0.5 hover:bg-leaf-800"
            >
              Get Started
              <Arrow className="transition-transform group-hover:translate-x-1" />
            </Link>
            <a
              href="#features"
              className="inline-flex items-center justify-center rounded-full bg-cream-50 px-7 py-4 font-bold text-leaf-800 ring-1 ring-leaf-200 transition hover:bg-leaf-50"
            >
              See how it works
            </a>
          </div>
          <ul className="mt-9 flex flex-wrap gap-x-6 gap-y-3 text-sm font-semibold text-ink-soft">
            {['Your own dealer prices', 'Schemes applied automatically', 'Order in Hindi or English'].map((t) => (
              <li key={t} className="flex items-center gap-2">
                <Check /> {t}
              </li>
            ))}
          </ul>
        </div>

        <HeroVisual />
      </div>
    </section>
  )
}

function HeroVisual() {
  return (
    <div className="relative mx-auto w-full max-w-lg animate-fade-up [animation-delay:150ms]" aria-hidden="true">
      <div className="relative rounded-[2.5rem] bg-leaf-700 p-6 shadow-2xl shadow-leaf-900/25 sm:p-8">
        {/* awning */}
        <div className="absolute inset-x-0 top-0 flex h-10 overflow-hidden rounded-t-[2.5rem]">
          {Array.from({ length: 10 }, (_, i) => (
            <div key={i} className={`flex-1 ${i % 2 ? 'bg-cream-50' : 'bg-mango-400'}`} />
          ))}
        </div>
        <div className="mt-8 rounded-3xl bg-cream-100 p-4 sm:p-5">
          <p className="px-1 text-xs font-bold uppercase tracking-wider text-leaf-700">Today’s shelf</p>
          <div className="mt-3 grid grid-cols-3 gap-3">
            {(['biscuits', 'tea', 'noodles', 'homecare', 'snacks', 'beverages'] as ArtKind[]).map((kind, i) => (
              <div
                key={kind}
                className={`flex items-center justify-center rounded-2xl bg-cream-50 p-2 shadow-sm ${i % 2 ? 'animate-float-slow' : 'animate-float'}`}
                style={{ animationDelay: `${i * 0.4}s` }}
              >
                <ProductArt kind={kind} className="h-16 w-16 sm:h-20 sm:w-20" />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* floating order card */}
      <div className="absolute -bottom-8 -left-2 w-60 animate-float-slow rounded-2xl bg-white p-4 shadow-xl shadow-leaf-900/10 ring-1 ring-leaf-100 sm:-left-10">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-ink-soft">New order</span>
          <span className="rounded-full bg-leaf-50 px-2 py-0.5 text-[10px] font-bold uppercase text-leaf-700">Approved</span>
        </div>
        <p className="mt-2 text-sm font-bold text-leaf-900">Glucose Biscuit 75g</p>
        <p className="text-xs text-ink-soft">10 cases + 1 case free</p>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-leaf-50">
          <div className="h-full w-3/4 rounded-full bg-gradient-to-r from-leaf-500 to-mango-400" />
        </div>
      </div>

      {/* floating message card */}
      <div className="absolute -right-2 -top-6 w-52 animate-float rounded-2xl bg-mango-300 p-4 shadow-xl shadow-mango-600/20 sm:-right-8">
        <p className="text-[10px] font-bold uppercase tracking-wider text-leaf-900/70">Order by message</p>
        <p className="mt-1 text-sm font-semibold leading-snug text-leaf-950">“bhaiya 5 peti biscuit, 2 peti chai patti bhej do”</p>
      </div>
    </div>
  )
}

function Section({ id, className = '', children }: { id?: string; className?: string; children: ReactNode }) {
  const ref = useReveal<HTMLDivElement>()
  return (
    <section id={id} className={`scroll-mt-20 ${className}`}>
      <div ref={ref} className="reveal mx-auto max-w-7xl px-5 sm:px-8">
        {children}
      </div>
    </section>
  )
}

function Heading({ eyebrow, title, text }: { eyebrow: string; title: string; text?: string }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <p className="text-sm font-bold uppercase tracking-wider text-mango-600">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-extrabold tracking-tight text-leaf-900 sm:text-4xl">{title}</h2>
      {text && <p className="mt-4 text-lg text-ink-soft">{text}</p>}
    </div>
  )
}

function Categories() {
  return (
    <Section id="categories" className="py-20">
      <Heading eyebrow="Categories" title="Everything your shelf needs" text="The FMCG range your distributor stocks, in one place, at your prices." />
      <div className="mt-12 grid grid-cols-2 gap-4 sm:grid-cols-4 sm:gap-5">
        {CATEGORIES.map((c) => (
          <div
            key={c.name}
            className={`group flex flex-col items-center rounded-3xl ${c.tint} px-4 pb-5 pt-6 text-center transition duration-300 hover:-translate-y-1 hover:shadow-lg hover:shadow-leaf-900/5`}
          >
            <ProductArt kind={c.kind} className="h-24 w-24 transition-transform duration-300 group-hover:scale-105 sm:h-28 sm:w-28" />
            <h3 className="mt-3 font-bold text-leaf-900">{c.name}</h3>
            <p className="mt-1 text-xs text-ink-soft sm:text-sm">{c.note}</p>
          </div>
        ))}
      </div>
    </Section>
  )
}

function Features() {
  return (
    <Section id="features" className="bg-leaf-50/60 py-20">
      <Heading eyebrow="Why DukaanFlow" title="Built for the way kirana stores order" />
      <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {BENEFITS.map((b) => (
          <div key={b.title} className="rounded-3xl bg-cream-50 p-6 ring-1 ring-leaf-100 transition duration-300 hover:-translate-y-1 hover:shadow-lg hover:shadow-leaf-900/5">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-mango-300 text-leaf-900">
              <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d={b.icon} />
              </svg>
            </div>
            <h3 className="mt-5 text-lg font-bold text-leaf-900">{b.title}</h3>
            <p className="mt-2 leading-relaxed text-ink-soft">{b.text}</p>
          </div>
        ))}
      </div>
    </Section>
  )
}

function HowItWorks() {
  return (
    <Section className="py-20">
      <Heading eyebrow="How it works" title="From empty shelf to delivered in three steps" />
      <ol className="mt-12 grid gap-6 md:grid-cols-3">
        {STEPS.map((s, i) => (
          <li key={s.title} className="relative rounded-3xl bg-white p-7 shadow-sm ring-1 ring-cream-200">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-leaf-700 text-lg font-extrabold text-mango-300">{i + 1}</span>
            <h3 className="mt-5 text-lg font-bold text-leaf-900">{s.title}</h3>
            <p className="mt-2 leading-relaxed text-ink-soft">{s.text}</p>
          </li>
        ))}
      </ol>
    </Section>
  )
}

function About() {
  return (
    <Section id="about" className="py-20">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <div>
          <p className="text-sm font-bold uppercase tracking-wider text-mango-600">About</p>
          <h2 className="mt-3 text-3xl font-extrabold tracking-tight text-leaf-900 sm:text-4xl">
            One ordering system for the distributor and every shop it serves
          </h2>
          <p className="mt-5 text-lg leading-relaxed text-ink-soft">
            DukaanFlow is built for local FMCG distributors and the kirana retailers they supply. Orders reach the
            distributor in one place, prices and schemes are calculated by the system, and stock and credit are checked
            before anything is approved, so there are fewer mistakes and fewer phone calls on both sides.
          </p>
        </div>
        <div className="grid gap-4">
          {ROLES.map((r, i) => (
            <div key={r.title} className="flex gap-4 rounded-3xl bg-cream-100 p-5 ring-1 ring-cream-200">
              <span className={`mt-1 h-3 w-3 shrink-0 rounded-full ${['bg-mango-400', 'bg-leaf-500', 'bg-leaf-800'][i]}`} />
              <div>
                <h3 className="font-bold text-leaf-900">{r.title}</h3>
                <p className="mt-1 text-ink-soft">{r.text}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Section>
  )
}

function CallToAction() {
  return (
    <Section className="py-10">
      <div className="relative overflow-hidden rounded-[2.5rem] bg-leaf-800 px-6 py-14 text-center sm:px-12">
        <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-mango-400/20 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-20 -left-10 h-64 w-64 rounded-full bg-leaf-400/20 blur-2xl" />
        <h2 className="relative text-3xl font-extrabold tracking-tight text-cream-50 sm:text-4xl">Ready to place your next order?</h2>
        <p className="relative mx-auto mt-4 max-w-xl text-lg text-leaf-100">
          Log in with the mobile number registered with your distributor. Your login code arrives on your registered email.
        </p>
        <Link
          to="/login"
          className="group relative mt-8 inline-flex items-center gap-2 rounded-full bg-mango-400 px-8 py-4 font-bold text-leaf-950 shadow-lg shadow-black/10 transition hover:-translate-y-0.5 hover:bg-mango-300"
        >
          Start ordering <Arrow className="transition-transform group-hover:translate-x-1" />
        </Link>
      </div>
    </Section>
  )
}

function Support() {
  const items = [
    { title: 'Login help', text: 'Your one-time code goes to the email registered with your distributor. Not getting it? Check spam, then ask the order desk to confirm your email.' },
    { title: 'Order questions', text: 'For changes to a placed order, deliveries or schemes, contact your distributor’s order desk or your salesman.' },
    { title: 'New retailer?', text: 'Ask your distributor to register your shop with your mobile number and email, then log in here.' },
  ]
  return (
    <Section id="support" className="py-20">
      <Heading eyebrow="Support" title="We’re here to help" />
      <div className="mt-12 grid gap-5 md:grid-cols-3">
        {items.map((s) => (
          <div key={s.title} className="rounded-3xl bg-white p-7 shadow-sm ring-1 ring-cream-200">
            <h3 className="text-lg font-bold text-leaf-900">{s.title}</h3>
            <p className="mt-2 leading-relaxed text-ink-soft">{s.text}</p>
          </div>
        ))}
      </div>
    </Section>
  )
}

function Footer() {
  return (
    <footer className="mt-10 bg-leaf-950 text-leaf-100">
      <div className="mx-auto grid max-w-7xl gap-10 px-5 py-14 sm:px-8 md:grid-cols-[1.5fr_1fr_1fr]">
        <div>
          <Logo light />
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-leaf-200/80">
            B2B ordering for FMCG distributors and kirana retailers: catalogue, dealer prices, schemes and order tracking in one place.
          </p>
        </div>
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wider text-mango-300">Explore</h3>
          <ul className="mt-4 space-y-2 text-sm">
            {NAV.map((n) => (
              <li key={n.href}>
                <a href={n.href} className="hover:text-cream-50">{n.label}</a>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wider text-mango-300">Account</h3>
          <ul className="mt-4 space-y-2 text-sm">
            <li><Link to="/login" className="hover:text-cream-50">Retailer login</Link></li>
            <li><Link to="/login?staff" className="hover:text-cream-50">Staff login</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-leaf-900">
        <p className="mx-auto max-w-7xl px-5 py-6 text-xs text-leaf-200/60 sm:px-8">© {YEAR} DukaanFlow. All rights reserved.</p>
      </div>
    </footer>
  )
}

function Arrow({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" className={`h-5 w-5 ${className}`} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 10h12M11 5l5 5-5 5" />
    </svg>
  )
}

function Check() {
  return (
    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-mango-300 text-leaf-900">
      <svg viewBox="0 0 20 20" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M5 10.5l3 3 7-7" />
      </svg>
    </span>
  )
}
