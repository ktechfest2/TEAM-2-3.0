import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckIcon, CopyIcon, KeyRoundIcon, UserPlusIcon, UsersIcon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { FormField } from '@/components/forms/form-field'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { useAuth } from '@/features/auth/auth-context'
import type { AccountResponse } from '@/features/auth/local-session'
import { ROLE_LABELS, ROLES, type Role } from '@/features/auth/roles'
import { useT } from '@/i18n/locale-provider'
import { api, ApiError } from '@/lib/api-client'

const ACCOUNTS_KEY = ['admin', 'accounts'] as const

type CreatedAccount = { account: AccountResponse; temporary_password: string | null }

function errorText(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback
}

function RolePicker({
  value,
  onChange,
  name,
}: {
  value: Role[]
  onChange: (next: Role[]) => void
  name: string
}) {
  const t = useT()
  return (
    <fieldset className="grid gap-2 sm:grid-cols-2">
      <legend className="sr-only">{t('Roles')}</legend>
      {ROLES.map((role) => (
        <label key={role} className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
          <input
            type="checkbox"
            name={name}
            value={role}
            checked={value.includes(role)}
            onChange={(event) =>
              onChange(event.target.checked ? [...value, role] : value.filter((item) => item !== role))
            }
            className="size-4 accent-primary"
          />
          {t(ROLE_LABELS[role])}
        </label>
      ))}
    </fieldset>
  )
}

function TemporaryPassword({ email, password, onDone }: { email: string; password: string; onDone: () => void }) {
  const t = useT()
  const [copied, setCopied] = useState(false)
  return (
    <Alert variant="warning" role="status">
      <KeyRoundIcon />
      <AlertTitle>{t('Temporary password for {email}', { email })}</AlertTitle>
      <AlertDescription className="space-y-3">
        <p>
          {t('Share it privately. It is shown only once, and the person must choose their own password when they first sign in.')}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <code className="rounded bg-background px-2 py-1 font-mono text-base" data-testid="temporary-password">
            {password}
          </code>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              void navigator.clipboard?.writeText(password).then(() => setCopied(true))
            }}
          >
            {copied ? <CheckIcon /> : <CopyIcon />}
            {copied ? t('Copied') : t('Copy')}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={onDone}>
            {t('Done')}
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  )
}

function CreateAccountForm({ onCreated }: { onCreated: (created: CreatedAccount) => void }) {
  const t = useT()
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [roles, setRoles] = useState<Role[]>(['observer'])
  const [error, setError] = useState<string | null>(null)
  const create = useMutation({
    mutationFn: () =>
      api.post<CreatedAccount>('/admin/users', {
        email: email.trim(),
        display_name: name.trim() || null,
        roles,
      }),
    onSuccess: (created) => {
      setEmail('')
      setName('')
      setRoles(['observer'])
      void queryClient.invalidateQueries({ queryKey: ACCOUNTS_KEY })
      onCreated(created)
    },
    onError: (err) => setError(errorText(err, t('The account could not be created.'))),
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return setError(t('Enter a valid email address.'))
    if (roles.length === 0) return setError(t('Choose at least one role.'))
    create.mutate()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <UserPlusIcon className="size-4 text-primary" aria-hidden />
          {t('Create an account')}
        </CardTitle>
        <CardDescription>
          {t('A temporary password is generated. Observers and party agents can then submit result-sheet evidence; reviewers verify it.')}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} noValidate className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField id="new-email" label={t('Email')} required>
              <Input
                id="new-email"
                type="email"
                autoComplete="off"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </FormField>
            <FormField id="new-name" label={t('Full name')}>
              <Input id="new-name" value={name} onChange={(event) => setName(event.target.value)} />
            </FormField>
          </div>
          <RolePicker value={roles} onChange={setRoles} name="new-roles" />
          {error && (
            <p role="alert" className="text-sm font-medium text-destructive">
              {error}
            </p>
          )}
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? <Spinner /> : <UserPlusIcon />}
            {t('Create account')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function AccountRow({
  account,
  isSelf,
  onPassword,
}: {
  account: AccountResponse
  isSelf: boolean
  onPassword: (email: string, password: string) => void
}) {
  const t = useT()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [roles, setRoles] = useState<Role[]>(account.roles as Role[])
  const [error, setError] = useState<string | null>(null)
  const refresh = () => queryClient.invalidateQueries({ queryKey: ACCOUNTS_KEY })

  const update = useMutation({
    mutationFn: (body: { roles?: Role[]; is_active?: boolean }) =>
      api.patch<AccountResponse>(`/admin/users/${account.id}`, body),
    onSuccess: () => {
      setEditing(false)
      setError(null)
      void refresh()
    },
    onError: (err) => setError(errorText(err, t('The change could not be saved.'))),
  })
  const reset = useMutation({
    mutationFn: () => api.post<{ temporary_password: string }>(`/admin/users/${account.id}/password-reset`),
    onSuccess: (data) => {
      onPassword(account.email, data.temporary_password)
      void refresh()
    },
    onError: (err) => setError(errorText(err, t('The password could not be reset.'))),
  })

  return (
    <li className="space-y-3 px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium">
            {account.display_name || account.email}
            {isSelf && <span className="ml-2 text-xs text-muted-foreground">({t('you')})</span>}
          </p>
          {account.display_name && <p className="truncate text-sm text-muted-foreground">{account.email}</p>}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {account.roles.map((role) => (
              <Badge key={role} variant="neutral">
                {t(ROLE_LABELS[role as Role] ?? role)}
              </Badge>
            ))}
            {!account.is_active && <Badge variant="destructive">{t('Disabled')}</Badge>}
            {account.must_change_password && <Badge variant="warning">{t('Temporary password')}</Badge>}
            {!account.has_password && <Badge variant="neutral">{t('External sign-in')}</Badge>}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {account.last_sign_in_at
              ? t('Last signed in {date}', { date: new Date(account.last_sign_in_at).toLocaleString() })
              : t('Never signed in')}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => setEditing((open) => !open)}>
            {editing ? t('Cancel') : t('Edit roles')}
          </Button>
          {!isSelf && (
            <Button type="button" size="sm" variant="outline" disabled={reset.isPending} onClick={() => reset.mutate()}>
              {reset.isPending && <Spinner />}
              {t('Reset password')}
            </Button>
          )}
          {!isSelf && (
            <Button
              type="button"
              size="sm"
              variant={account.is_active ? 'destructive' : 'outline'}
              disabled={update.isPending}
              onClick={() => update.mutate({ is_active: !account.is_active })}
            >
              {account.is_active ? t('Disable') : t('Enable')}
            </Button>
          )}
        </div>
      </div>
      {editing && (
        <div className="space-y-3 rounded-md border bg-muted/30 p-3">
          <RolePicker value={roles} onChange={setRoles} name={`roles-${account.id}`} />
          <Button
            type="button"
            size="sm"
            disabled={update.isPending || roles.length === 0}
            onClick={() => update.mutate({ roles })}
          >
            {update.isPending && <Spinner />}
            {t('Save roles')}
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm font-medium text-destructive">
          {error}
        </p>
      )}
    </li>
  )
}

export function AccountsPage() {
  const t = useT()
  const { user, provider } = useAuth()
  const [secret, setSecret] = useState<{ email: string; password: string } | null>(null)
  const accounts = useQuery({
    queryKey: ACCOUNTS_KEY,
    queryFn: () => api.get<AccountResponse[]>('/admin/users'),
  })

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('Accounts and roles')}
        description={t('Manage staff, observers and party agents. Every change is logged.')}
      />
      {provider === 'supabase' && (
        <Alert variant="info">
          <AlertTitle>{t('Supabase sign-in is active')}</AlertTitle>
          <AlertDescription>
            {t('Accounts created here use VoteTrace passwords. Supabase users keep the roles set in their Supabase profile.')}
          </AlertDescription>
        </Alert>
      )}
      {secret && <TemporaryPassword email={secret.email} password={secret.password} onDone={() => setSecret(null)} />}
      <CreateAccountForm
        onCreated={(created) =>
          created.temporary_password &&
          setSecret({ email: created.account.email, password: created.temporary_password })
        }
      />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <UsersIcon className="size-4 text-primary" aria-hidden />
            {t('All accounts')}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {accounts.isPending ? (
            <LoadingState className="py-10" />
          ) : accounts.isError ? (
            <ErrorState
              message={errorText(accounts.error, t('Accounts could not be loaded.'))}
              onRetry={() => void accounts.refetch()}
            />
          ) : accounts.data.length === 0 ? (
            <EmptyState icon={UsersIcon} title={t('No accounts yet')} description={t('Create the first account above.')} />
          ) : (
            <ul className="divide-y">
              {accounts.data.map((account) => (
                <AccountRow
                  key={`${account.id}-${account.roles.join(',')}`}
                  account={account}
                  isSelf={account.id === user?.id}
                  onPassword={(email, password) => setSecret({ email, password })}
                />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
