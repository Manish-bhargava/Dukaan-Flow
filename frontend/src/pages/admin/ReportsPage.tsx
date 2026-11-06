import { useState } from 'react'
import { admin } from '../../api/admin'
import { useLoad, useToken } from '../../auth/useApi'
import { Button, ErrorBox } from '../../components/ui'
import { saveBlob } from '../desk/deskFormat'
import { daysAgoIst, todayIst } from './adminFormat'
import { AdminPage, Card, DataTable, Field, FilterBar, Loaded, Select, TextInput } from './adminUi'
import { useAction } from './adminHooks'

/** Business reports with date filters and CSV export (all figures come from the server). */
export function ReportsPage() {
  const token = useToken()
  const list = useLoad((t, s) => admin.reportList(t, s), 'report-list')
  const [name, setName] = useState(new URLSearchParams(window.location.search).get('report') ?? 'sales-by-date')
  const [from, setFrom] = useState(daysAgoIst(29))
  const [to, setTo] = useState(todayIst())
  const report = useLoad((t, s) => admin.report(t, name, { from_date: from || undefined, to_date: to || undefined }, s), `${name}|${from}|${to}`)
  const download = useAction()
  const reports = list.state.status === 'ready' ? list.state.data : []
  const dated = reports.find((r) => r.name === name)?.uses_dates ?? true

  return (
    <AdminPage title="Reports" subtitle="Sales are confirmed orders, by confirmation date (India time)."
      actions={<Button variant="secondary" busy={download.busy} onClick={() => download.run(async () => {
        const { blob, filename } = await admin.reportCsv(token, name, dated ? { from_date: from || undefined, to_date: to || undefined } : {})
        saveBlob(blob, filename)
      })}>Export CSV</Button>}>
      <FilterBar>
        <Select label="Report" value={name} onChange={setName} className="sm:min-w-[260px]" options={reports.map((r) => [r.name, r.title] as [string, string])} />
        {dated && <>
          <Field label="From"><TextInput type="date" value={from} onChange={setFrom} /></Field>
          <Field label="To"><TextInput type="date" value={to} onChange={setTo} /></Field>
          <div className="flex gap-2">
            {[['7 days', 6], ['30 days', 29], ['90 days', 89]].map(([label, n]) => (
              <Button key={label} variant="secondary" onClick={() => { setFrom(daysAgoIst(Number(n))); setTo(todayIst()) }}>{label}</Button>
            ))}
          </div>
        </>}
      </FilterBar>
      {download.error && <ErrorBox message={download.error} />}
      <Loaded state={report.state} reload={report.reload} label="Running report…">
        {(r) => (
          <Card title={r.title} actions={<span className="text-sm text-ink-soft">{r.rows.length} rows{r.uses_dates ? '' : ' · current position (no dates)'}</span>} padded={false}>
            <DataTable rows={r.rows.map((row, i) => ({ i, row }))} rowKey={(x) => String(x.i)} loading={report.loading} empty="No data for these dates"
              columns={r.columns.map((c, ci) => ({
                header: c,
                align: ci > 0 && /^-?\d+(\.\d+)?$/.test(String(r.rows[0]?.[ci] ?? '')) ? 'right' as const : undefined,
                cell: (x: { row: (string | number)[] }) => {
                  const v = x.row[ci]
                  return /sales|value|limit|outstanding/i.test(c) && v !== '' && !Number.isNaN(Number(v))
                    ? Number(v).toLocaleString('en-IN', { style: 'currency', currency: 'INR' }) : String(v)
                },
              }))} />
          </Card>
        )}
      </Loaded>
    </AdminPage>
  )
}
