import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { AuthUser } from '../api/auth'
import { ApiError } from '../api/client'
import type { OrderStatus } from '../api/orders'
import { fetchSalesmanHome, fetchSyncBundle, reportSyncStatus, sendSalesmanOrder, sendVisit, type SalesmanHome, type SyncBundle } from '../api/salesman'
import { useAuth } from '../auth/AuthContext'
import { isExpired } from '../auth/session'
import { idbAll, idbDelete, idbGet, idbPut } from './idb'
import { newUuid } from './ids'

/**
 * Salesman offline mode. All data the salesman works with comes from IndexedDB:
 * - the sync bundle (assigned retailers, products, their prices, stock, schemes, credit),
 *   refreshed whenever the phone is online;
 * - the order outbox: every order is saved on the phone first, then sent with its
 *   device-generated id, so a retry can never create a duplicate. It is marked Synced only
 *   after the backend confirms it; nothing is ever dropped without the salesman deciding;
 * - visits, sent the same way.
 */
export type SyncStatus = 'saved_offline' | 'pending_sync' | 'syncing' | 'synced' | 'sync_failed'

export interface LocalOrderItem {
  product_id: string
  sku: string
  name: string
  pack_size: string
  order_unit: string
  quantity: number
  expected_unit_price: string // the retailer's dealer price shown on the phone
  price_basis: 'PIECE' | 'CASE'
  case_price: string
  /** The product's active schemes shown on the phone when the order was created. */
  schemes?: { id: string; description: string }[]
}

export interface LocalOrder {
  client_order_id: string
  salesman_id: string
  retailer_id: string
  shop_name: string
  items: LocalOrderItem[]
  remarks: string | null
  created_at: string
  created_offline: boolean
  status: SyncStatus
  last_error: string | null
  attempts: number
  server: { id: string; order_number: string; status: OrderStatus; grand_total: string; hold_reason: string | null } | null
}

export interface LocalVisit {
  id: string
  salesman_id: string
  retailer_id: string
  shop_name: string
  started_at: string
  ended_at: string | null
  outcome: 'ORDER_PLACED' | 'NO_ORDER' | null
  client_order_id: string | null
  synced: boolean
  /** The server has linked this visit to its order (or it has none). */
  linked?: boolean
}

/** What a sync or download did, shown to the salesman. */
export interface ActionResult {
  ok: boolean
  message: string
}

/** Today's work: the server's numbers plus anything on this phone not synced yet. */
export interface TodaySummary {
  fromServer: boolean // false: no server summary yet (never online today)
  assignedRetailers: number
  visitsToday: number
  shopsVisitedToday: number // distinct retailers visited today (several visits to one shop count once)
  ordersToday: number
  visits: { id: string; retailer_id: string; shop_name: string; started_at: string; ended_at: string | null; outcome: LocalVisit['outcome']; synced: boolean }[]
}

interface SalesmanContextValue {
  online: boolean
  lastSyncAt: string | null // last successful exchange with the backend (orders sent or data downloaded)
  today: TodaySummary
  bundle: SyncBundle | null
  bundleError: string | null
  orders: LocalOrder[]
  visits: LocalVisit[]
  syncing: boolean
  downloading: boolean
  needsLogin: boolean
  pendingCount: number
  refreshBundle: () => Promise<ActionResult>
  syncNow: () => Promise<ActionResult>
  saveOrder: (order: Omit<LocalOrder, 'salesman_id' | 'status' | 'last_error' | 'attempts' | 'server' | 'created_at' | 'created_offline' | 'client_order_id'>) => Promise<LocalOrder>
  retryOrder: (clientOrderId: string) => Promise<void>
  discardOrder: (clientOrderId: string) => Promise<void>
  startVisit: (retailerId: string, shopName: string) => Promise<LocalVisit>
  endVisit: (visitId: string, outcome: 'ORDER_PLACED' | 'NO_ORDER', clientOrderId?: string) => Promise<void>
}

const SalesmanContext = createContext<SalesmanContextValue | null>(null)

interface PhoneData {
  bundle: SyncBundle | null
  home: SalesmanHome | null
  lastSyncAt: string | null
  orders: LocalOrder[]
  visits: LocalVisit[]
}

/** This salesman's data saved on the phone (newest first). */
async function readPhoneData(userId: string): Promise<PhoneData> {
  const [bundle, home, lastSyncAt, orders, visits] = await Promise.all([
    idbGet<SyncBundle>('kv', `bundle:${userId}`),
    idbGet<SalesmanHome>('kv', `home:${userId}`),
    idbGet<string>('kv', `lastsync:${userId}`),
    idbAll<LocalOrder>('orders'),
    idbAll<LocalVisit>('visits'),
  ])
  return {
    bundle: bundle ?? null,
    home: home ?? null,
    lastSyncAt: lastSyncAt ?? null,
    orders: orders.filter((x) => x.salesman_id === userId).sort((a, z) => z.created_at.localeCompare(a.created_at)),
    visits: visits.filter((x) => x.salesman_id === userId).sort((a, z) => z.started_at.localeCompare(a.started_at)),
  }
}
const RETRY_MS = 30_000

/** A plain reason for a temporary sync failure. */
function whyNotSent(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return 'No connection to the server'
    if (err.status === 401) return 'Your login has expired'
    if (err.status === 429) return 'Too many requests, please wait a moment'
    if (err.status >= 500) return 'The server had a problem'
  }
  return 'The order could not be sent right now'
}

const TRANSIENT = (err: unknown) =>
  !(err instanceof ApiError) || err.status === 0 || err.status === 401 || err.status === 429 || err.status >= 500

export function SalesmanProvider({ user, children }: { user: AuthUser; children: ReactNode }) {
  const { state } = useAuth()
  const session = state.status === 'authenticated' ? state.session : null
  const token = session && !isExpired(session) ? session.token : null
  const [online, setOnline] = useState(navigator.onLine)
  const [bundle, setBundle] = useState<SyncBundle | null>(null)
  const [home, setHome] = useState<SalesmanHome | null>(null)
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null)
  // The calendar day, so "today" rolls over at midnight while the app stays open.
  const [day, setDay] = useState(() => new Date().toDateString())
  useEffect(() => {
    const timer = window.setInterval(() => setDay(new Date().toDateString()), 60_000)
    return () => window.clearInterval(timer)
  }, [])
  const [bundleError, setBundleError] = useState<string | null>(null)
  const [orders, setOrders] = useState<LocalOrder[]>([])
  const [visits, setVisits] = useState<LocalVisit[]>([])
  const [syncing, setSyncing] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [loginRejected, setNeedsLogin] = useState(false)
  // Expired login (kept for offline work) or the server refused the token: log in to sync.
  const needsLogin = !token || loginRejected
  const syncLock = useRef(false)
  const bundleKey = `bundle:${user.id}`

  const apply = useCallback((data: PhoneData) => {
    setBundle(data.bundle)
    setHome(data.home)
    setLastSyncAt(data.lastSyncAt)
    setOrders(data.orders)
    setVisits(data.visits)
  }, [])
  const reload = useCallback(async () => apply(await readPhoneData(user.id)), [apply, user.id])

  const markSynced = useCallback(async () => {
    const at = new Date().toISOString()
    await idbPut('kv', at, `lastsync:${user.id}`)
    setLastSyncAt(at)
  }, [user.id])

  const refreshBundle = useCallback(async (): Promise<ActionResult> => {
    if (!navigator.onLine) return { ok: false, message: 'You are offline. Using the data saved on this phone.' }
    if (!token) return { ok: false, message: 'Your login has expired. Log in again to download the latest data.' }
    setDownloading(true)
    try {
      const [fresh, summary] = await Promise.all([fetchSyncBundle(token), fetchSalesmanHome(token)])
      await idbPut('kv', fresh.data, bundleKey)
      await idbPut('kv', summary.data, `home:${user.id}`)
      setBundle(fresh.data)
      setHome(summary.data)
      setBundleError(null)
      await markSynced()
      return { ok: true, message: `Latest data downloaded: ${fresh.data.retailers.length} retailers, ${fresh.data.products.length} products.` }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not download data'
      setBundleError(message)
      if (err instanceof ApiError && err.status === 401) setNeedsLogin(true)
      return { ok: false, message }
    } finally {
      setDownloading(false)
    }
  }, [token, bundleKey, user.id, markSynced])

  const syncNow = useCallback(async (): Promise<ActionResult> => {
    if (!navigator.onLine) return { ok: false, message: 'You are offline. Orders stay saved on this phone and sync automatically when internet is back.' }
    if (!token) return { ok: false, message: 'Your login has expired. Log in again to sync. Your saved orders are safe on this phone.' }
    if (syncLock.current) return { ok: true, message: 'A sync is already running.' }
    syncLock.current = true
    setSyncing(true)
    let sentOrders = 0
    let sentVisits = 0
    let failedOrders = 0
    let transientError: string | null = null
    try {
      // Back online: everything saved offline is now pending sync.
      for (const o of (await idbAll<LocalOrder>('orders')).filter((x) => x.salesman_id === user.id && x.status === 'saved_offline')) {
        await idbPut('orders', { ...o, status: 'pending_sync' })
      }
      await reload()
      const all = (await idbAll<LocalOrder>('orders')).filter((o) => o.salesman_id === user.id)
      for (const order of all.filter((o) => o.status === 'pending_sync' || o.status === 'syncing')) {
        await idbPut('orders', { ...order, status: 'syncing' })
        await reload()
        try {
          const saved = (await sendSalesmanOrder(token, {
            retailer_id: order.retailer_id,
            items: order.items.map((i) => ({
              product_id: i.product_id, quantity: i.quantity, unit: i.order_unit, expected_unit_price: i.expected_unit_price,
              expected_scheme_ids: i.schemes?.map((sch) => sch.id),
            })),
            remarks: order.remarks,
            client_order_id: order.client_order_id,
            created_offline: order.created_offline,
            client_created_at: order.created_at,
          })).data
          await idbPut('orders', {
            ...order, status: 'synced', last_error: null, attempts: order.attempts + 1,
            server: { id: saved.id, order_number: saved.order_number, status: saved.status, grand_total: saved.grand_total, hold_reason: saved.hold_reason },
          })
          sentOrders++
          // A visit sent before this order synced could not be linked to it: send it again.
          for (const v of (await idbAll<LocalVisit>('visits')).filter((x) => x.client_order_id === order.client_order_id && x.synced && !x.linked)) {
            await idbPut('visits', { ...v, synced: false })
          }
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Sync failed'
          const transient = TRANSIENT(err)
          await idbPut('orders', {
            ...order, attempts: order.attempts + 1, last_error: message,
            status: transient ? (navigator.onLine ? 'pending_sync' : 'saved_offline') : 'sync_failed',
          })
          if (err instanceof ApiError && err.status === 401) setNeedsLogin(true)
          if (transient) {
            transientError = whyNotSent(err)
            break // network or server trouble: try again later, keep the order
          }
          failedOrders++
        }
      }
      // Visits after orders, so a visit can be linked to the order placed during it. A visit
      // record is done once the server has its current state (it is sent again if it changes).
      if (!transientError) {
        const outbox = new Set((await idbAll<LocalOrder>('orders')).map((o) => o.client_order_id))
        for (const visit of (await idbAll<LocalVisit>('visits')).filter((v) => v.salesman_id === user.id && !v.synced)) {
          try {
            const res = (await sendVisit(token, {
              id: visit.id, retailer_id: visit.retailer_id, started_at: visit.started_at, ended_at: visit.ended_at,
              outcome: visit.outcome, client_order_id: visit.client_order_id,
            })).data
            sentVisits++
            const linked = !visit.client_order_id || res.order_id !== null || !outbox.has(visit.client_order_id)
            await idbPut('visits', { ...visit, synced: true, linked })
          } catch (err) {
            if (TRANSIENT(err)) {
              transientError = whyNotSent(err)
              break
            }
            await idbPut('visits', { ...visit, synced: true, linked: true }) // refused (e.g. unassigned now): don't retry forever
          }
        }
      }
      if (!transientError) await markSynced()
    } finally {
      syncLock.current = false
      setSyncing(false)
      await reload()
    }
    if (sentOrders + sentVisits > 0) await refreshBundle() // stock, credit and today's counts changed

    const mine = (await idbAll<LocalOrder>('orders')).filter((o) => o.salesman_id === user.id)
    const left = mine.filter((o) => o.status !== 'synced').length
    if (!transientError && navigator.onLine) {
      const failed = mine.filter((o) => o.status === 'sync_failed')
      const visitsLeft = (await idbAll<LocalVisit>('visits')).filter((v) => v.salesman_id === user.id && !v.synced).length
      void reportSyncStatus(token, {
        pending_orders: left - failed.length, failed_orders: failed.length, pending_visits: visitsLeft,
        last_error: failed[0]?.last_error?.slice(0, 500) ?? null,
      }).catch(() => undefined) // monitoring only: never disturbs the salesman
    }
    const sent = [sentOrders && `${sentOrders} order${sentOrders === 1 ? '' : 's'}`, sentVisits && `${sentVisits} visit record${sentVisits === 1 ? '' : 's'}`].filter(Boolean).join(' and ')
    if (transientError) {
      return { ok: false, message: `${sent ? `Sent ${sent}. ` : ''}${transientError}. Orders stay saved on this phone and will retry automatically.` }
    }
    if (failedOrders) {
      return { ok: false, message: `${sent ? `Sent ${sent}. ` : ''}${failedOrders} order${failedOrders === 1 ? '' : 's'} could not be sent. See Failed.` }
    }
    return { ok: true, message: sent ? `Synced ${sent}.${left ? '' : ' Everything is up to date.'}` : 'Everything is already up to date.' }
  }, [token, user.id, reload, refreshBundle, markSynced])

  // Load the phone's data, then sync and refresh when online.
  useEffect(() => {
    void readPhoneData(user.id).then((data) => {
      apply(data)
      if (navigator.onLine) {
        void syncNow()
        void refreshBundle()
      }
    })
  }, [user.id, apply, syncNow, refreshBundle])

  // Connectivity: sync as soon as the connection is back.
  useEffect(() => {
    const up = () => {
      setOnline(true)
      void syncNow().then(() => refreshBundle())
    }
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [syncNow, refreshBundle])

  // Things on this phone the server does not have yet. A visit whose order is still unsent is
  // covered by that order (counted once).
  const unsentOrderIds = new Set(orders.filter((o) => o.status !== 'synced').map((o) => o.client_order_id))
  const pendingCount = unsentOrderIds.size
    + visits.filter((v) => !v.synced && !(v.client_order_id && unsentOrderIds.has(v.client_order_id))).length

  const today = useMemo<TodaySummary>(() => {
    const todayStr = day
    const isToday = (iso: string) => new Date(iso).toDateString() === todayStr
    const serverToday = home && new Date(home.date + 'T12:00:00').toDateString() === todayStr ? home : null
    const serverIds = new Set(serverToday?.todays_visits.map((v) => v.id) ?? [])
    const localVisits = visits.filter((v) => isToday(v.started_at) && (!v.synced || !serverToday) && !serverIds.has(v.id))
    const localOrders = orders.filter((o) => isToday(o.created_at) && (o.status !== 'synced' || !serverToday))
    const latest = new Map(visits.map((v) => [v.id, v]))
    const shopsVisited = new Set([...localVisits.map((v) => v.retailer_id), ...(serverToday?.todays_visits ?? []).map((v) => v.retailer_id)])
    return {
      shopsVisitedToday: shopsVisited.size,
      fromServer: Boolean(serverToday),
      assignedRetailers: bundle?.retailers.length ?? serverToday?.assigned_retailers ?? 0,
      visitsToday: (serverToday?.visits_today ?? 0) + localVisits.length,
      ordersToday: (serverToday?.orders_today ?? 0) + localOrders.length,
      visits: [
        ...localVisits.map((v) => ({ ...v, synced: false })),
        ...(serverToday?.todays_visits ?? []).map((v) => {
          const mine = latest.get(v.id) // the phone may know a newer state (e.g. ended, not yet synced)
          return mine && !mine.synced ? { ...v, ended_at: mine.ended_at, outcome: mine.outcome, synced: false } : { ...v, synced: true }
        }),
      ].sort((a, z) => z.started_at.localeCompare(a.started_at)),
    }
  }, [home, bundle, visits, orders, day])

  // Retry waiting items periodically while online (temporary network/server failures).
  useEffect(() => {
    if (!online || pendingCount === 0) return
    const timer = window.setInterval(() => void syncNow(), RETRY_MS)
    return () => window.clearInterval(timer)
  }, [online, pendingCount, syncNow])

  const saveOrder = useCallback<SalesmanContextValue['saveOrder']>(async (draft) => {
    const offline = !navigator.onLine
    const order: LocalOrder = {
      ...draft,
      client_order_id: newUuid().replaceAll('-', ''),
      salesman_id: user.id,
      created_at: new Date().toISOString(),
      created_offline: offline,
      status: offline ? 'saved_offline' : 'pending_sync',
      last_error: null,
      attempts: 0,
      server: null,
    }
    await idbPut('orders', order) // persisted before anything else happens
    await reload()
    if (!offline) void syncNow()
    return order
  }, [user.id, reload, syncNow])

  const retryOrder = useCallback(async (id: string) => {
    const order = await idbGet<LocalOrder>('orders', id)
    if (!order || order.status === 'synced') return
    await idbPut('orders', { ...order, status: navigator.onLine ? 'pending_sync' : 'saved_offline', last_error: null })
    await reload()
    void syncNow()
  }, [reload, syncNow])

  const discardOrder = useCallback(async (id: string) => {
    const order = await idbGet<LocalOrder>('orders', id)
    if (!order || order.status === 'synced' || order.status === 'syncing') return
    await idbDelete('orders', id)
    await reload()
  }, [reload])

  const startVisit = useCallback(async (retailerId: string, shopName: string) => {
    const visit: LocalVisit = {
      id: newUuid(), salesman_id: user.id, retailer_id: retailerId, shop_name: shopName,
      started_at: new Date().toISOString(), ended_at: null, outcome: null, client_order_id: null, synced: false,
    }
    await idbPut('visits', visit)
    await reload()
    void syncNow()
    return visit
  }, [user.id, reload, syncNow])

  const endVisit = useCallback(async (visitId: string, outcome: 'ORDER_PLACED' | 'NO_ORDER', clientOrderId?: string) => {
    const visit = await idbGet<LocalVisit>('visits', visitId)
    if (!visit) return
    await idbPut('visits', { ...visit, ended_at: new Date().toISOString(), outcome, client_order_id: clientOrderId ?? null, synced: false })
    await reload()
    void syncNow()
  }, [reload, syncNow])

  const value = useMemo<SalesmanContextValue>(() => ({
    online, lastSyncAt, today, bundle, bundleError, orders, visits, syncing, downloading, needsLogin, pendingCount,
    refreshBundle, syncNow, saveOrder, retryOrder, discardOrder, startVisit, endVisit,
  }), [online, lastSyncAt, today, bundle, bundleError, orders, visits, syncing, downloading, needsLogin, pendingCount,
    refreshBundle, syncNow, saveOrder, retryOrder, discardOrder, startVisit, endVisit])
  return <SalesmanContext.Provider value={value}>{children}</SalesmanContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSalesman(): SalesmanContextValue {
  const context = useContext(SalesmanContext)
  if (!context) throw new Error('useSalesman must be used inside <SalesmanProvider>')
  return context
}
