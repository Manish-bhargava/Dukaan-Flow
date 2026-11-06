import { t } from '../../i18n'
import type { ReactNode } from 'react'
import { fetchMyProfile, type RetailerProfile } from '../../api/retailers'
import { useLoad } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { ErrorBox, Loading, Notice } from '../../components/ui'
import { CREDIT_EXPLANATION, CREDIT_LEVEL_STYLES, creditLevel, plural, rupees } from '../../format'

/** Shared loader/shell for the two account pages (both read GET /retailers/me). */
function AccountPage({ title, children }: { title: string; children: (p: RetailerProfile) => ReactNode }) {
  const profile = useLoad((t, s) => fetchMyProfile(t, s), 'my-profile')
  return (
    <>
      <Link to="/home" className="text-sm font-bold text-leaf-700">{t('← Back to catalogue')}</Link>
      <h1 className="mt-3 text-xl font-extrabold text-ink">{title}</h1>
      <div className="mt-4">
        {profile.state.status === 'error' ? (
          <ErrorBox message={profile.state.message} onRetry={profile.reload} />
        ) : profile.state.status === 'loading' ? (
          <Loading />
        ) : (
          children(profile.state.data)
        )}
      </div>
    </>
  )
}

/** "View profile": the retailer's own details and purchase summary. */
export function ProfilePage() {
  return (
    <AccountPage title={t('My profile')}>
      {(p) => (
        <div className="grid items-start gap-6 lg:grid-cols-2">
          <section aria-labelledby="shop-title" className="rounded-xl border border-gray-200 p-4">
            <h2 id="shop-title" className="font-extrabold text-ink">{t('Shop details')}</h2>
            <dl className="mt-2 divide-y divide-gray-100 text-sm">
              <Row label="Shop name">{p.shop_name}</Row>
              <Row label="Owner">{p.owner_name}</Row>
              <Row label="Retailer ID"><span className="break-all font-mono text-xs">{p.id}</span></Row>
              <Row label="Registered mobile">+91 {p.phone}</Row>
              <Row label="Address">{p.address}, {p.city}</Row>
              {p.gstin && <Row label="GSTIN">{p.gstin}</Row>}
              <Row label={t('Your salesman')}>
                {p.assigned_salesman ? (
                  <>
                    {p.assigned_salesman.name} ·{' '}
                    <a href={`tel:+91${p.assigned_salesman.phone}`} className="font-bold text-leaf-700 underline">+91 {p.assigned_salesman.phone}</a>
                  </>
                ) : (
                  'Not assigned'
                )}
              </Row>
            </dl>
          </section>

          <section aria-labelledby="purchases-title" className="rounded-xl border border-gray-200 p-4">
            <h2 id="purchases-title" className="font-extrabold text-ink">Purchases</h2>
            <dl className="mt-2 divide-y divide-gray-100 text-sm">
              <Row label={t('Total purchased')} hint={plural(p.purchases.confirmed_orders, 'confirmed order')}>
                <span className="text-base font-extrabold">{rupees(p.purchases.total_purchased)}</span>
              </Row>
              <Row
                label="Total orders"
                hint={`${p.purchases.confirmed_orders} confirmed · ${p.purchases.under_review_orders} under review · ${p.purchases.rejected_orders} rejected`}
              >
                {p.purchases.total_orders}
              </Row>
              {p.purchases.under_review_orders > 0 && (
                <Row label="Under review" hint="Not counted as purchased until confirmed">
                  {rupees(p.purchases.under_review_amount)}
                </Row>
              )}
            </dl>
            <p className="mt-2 text-sm">
              <Link to="/orders" className="font-bold text-leaf-700 underline">See my orders</Link>
            </p>
          </section>
        </div>
      )}
    </AccountPage>
  )
}

/** "Credit details": only the retailer's own credit. */
export function CreditPage() {
  return (
    <AccountPage title={t('Credit details')}>
      {(p) => {
        const c = p.credit
        if (!c) {
          return <Notice tone="warn">You do not have a credit account yet. Please contact the distributor.</Notice>
        }
        const level = creditLevel(c.available_credit, c.credit_limit)
        return (
          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <div className="space-y-4">
            <section className={`rounded-xl p-6 ring-1 ${CREDIT_LEVEL_STYLES[level].pill}`}>
              <p className="text-sm font-semibold">{Number(c.available_credit) > 0 ? t('Credit left') : t('Credit limit reached')}</p>
              <p className="text-3xl font-extrabold">{rupees(Math.max(0, Number(c.available_credit)))}</p>
              <p className="text-sm">{t('of your {limit} credit limit', { limit: rupees(c.credit_limit) })}</p>
            </section>
            {!p.can_place_orders && <CreditBlockedNotice profile={p} />}
            </div>

            <section aria-labelledby="credit-title" className="rounded-xl border border-gray-200 p-4">
              <h2 id="credit-title" className="font-extrabold text-ink">How it adds up</h2>
              <dl className="mt-2 divide-y divide-gray-100 text-sm">
                <Row label={t('Credit limit')}>{rupees(c.credit_limit)}</Row>
                <Row label={t('Outstanding amount')} hint={t('Confirmed orders not paid yet')}>− {rupees(c.current_outstanding)}</Row>
                <Row label={t('Held for orders under review')} hint={t('Comes back if the order desk rejects them')}>
                  − {rupees(c.reserved_for_review)}
                </Row>
                <Row label={t('Credit left')}>
                  <span className={`text-base font-extrabold ${CREDIT_LEVEL_STYLES[level].text}`}>
                    {rupees(Math.max(0, Number(c.available_credit)))}
                  </span>
                </Row>
              </dl>
              <p className="mt-2 text-xs leading-relaxed text-ink-soft">{CREDIT_EXPLANATION}</p>
            </section>
          </div>
        )
      }}
    </AccountPage>
  )
}

function CreditBlockedNotice({ profile }: { profile: RetailerProfile }) {
  const s = profile.assigned_salesman
  return (
    <Notice tone="warn">
      <p className="font-bold">{t('Your credit limit has been reached.')}</p>
      <p className="mt-1">
        You can still browse products and see your orders, but new orders cannot be placed until your outstanding amount is
        reduced. Please contact {s ? <>your salesman <b>{s.name}</b> (<a href={`tel:+91${s.phone}`} className="font-bold underline">+91 {s.phone}</a>) or </> : ''}
        the distributor’s order desk.
      </p>
    </Notice>
  )
}

function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5">
      <dt className="text-ink-soft">
        {label}
        {hint && <span className="block text-xs">{hint}</span>}
      </dt>
      <dd className="text-right font-semibold text-ink">{children}</dd>
    </div>
  )
}
