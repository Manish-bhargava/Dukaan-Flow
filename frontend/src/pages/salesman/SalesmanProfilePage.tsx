import type { AuthUser } from '../../api/auth'
import { useAuth } from '../../auth/AuthContext'
import { ROLE_LABELS } from '../../api/auth'
import { ago, plural } from '../../format'
import { useSalesman } from '../../salesman/SalesmanContext'
import { Avatar, Card, IconTile, ListGroup, ListRow, PrimaryButton, Screen, SectionLabel } from '../../salesman/ui'

/** The salesman's own details and work information (all from data already on the phone). */
export function SalesmanProfilePage({ user }: { user: AuthUser }) {
  const { signOut } = useAuth()
  const { bundle, pendingCount, today } = useSalesman()
  const areas = [...new Set((bundle?.retailers ?? []).map((r) => r.city))].sort()

  return (
    <Screen title="Profile">
      <div className="grid items-start gap-5 lg:grid-cols-2">
      <div className="space-y-5">
      <Card className="flex flex-col items-center py-6 text-center">
        <Avatar name={user.name} size="h-20 w-20 text-2xl" />
        <p className="mt-3 text-[20px] font-extrabold text-ink">{user.name}</p>
        <p className="text-[14px] font-medium text-ink-soft">{ROLE_LABELS[user.role]}</p>
      </Card>

      <div>
        <SectionLabel>Contact</SectionLabel>
        <ListGroup>
          <ListRow href={`tel:+91${user.phone}`} leading={<IconTile name="phone" tone="gray" />} title={`+91 ${user.phone}`} subtitle="Registered mobile (login)" />
          <ListRow href={user.email ? `mailto:${user.email}` : undefined} leading={<IconTile name="mail" tone="gray" />} title={user.email ?? 'Not set'} subtitle="Email" />
        </ListGroup>
      </div>
      </div>
      <div className="space-y-5">

      <div>
        <SectionLabel>Work</SectionLabel>
        <ListGroup>
          <ListRow to="/salesman/retailers" leading={<IconTile name="store" />} title={plural(today.assignedRetailers, 'assigned retailer')}
            subtitle={areas.length ? `Area: ${areas.join(', ')}` : undefined} />
          <ListRow to="/home" leading={<IconTile name="clock" />} title={plural(today.visitsToday, 'visit')} subtitle="Today" />
          <ListRow to="/salesman/orders" leading={<IconTile name="orders" />} title={plural(today.ordersToday, 'order')} subtitle="Placed today" />
        </ListGroup>
      </div>

      <div>
        <SectionLabel>This phone</SectionLabel>
        <ListGroup>
          <ListRow to="/salesman/sync" leading={<IconTile name="sync" tone={pendingCount ? 'mango' : 'leaf'} />}
            title={pendingCount ? `${pendingCount} waiting to sync` : 'Everything synced'}
            subtitle={bundle ? `Data downloaded ${ago(bundle.synced_at)}` : 'No data downloaded yet'} />
        </ListGroup>
      </div>

      <PrimaryButton tone="danger" onClick={() => {
        if (pendingCount === 0 || window.confirm('Some orders are not synced yet. They stay saved on this phone and sync after you log in again. Log out?')) signOut()
      }}>
        Log out
      </PrimaryButton>
      </div>
      </div>
    </Screen>
  )
}
