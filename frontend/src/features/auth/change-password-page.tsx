import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowLeftIcon, KeyRoundIcon } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'
import { z } from 'zod'
import { usePageTitle, useRouteMeta } from '@/app/seo'
import { Logo } from '@/components/brand/logo'
import { describedBy, FormField } from '@/components/forms/form-field'
import { LoadingState } from '@/components/feedback/states'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { useAuth } from '@/features/auth/auth-context'
import { destinationFor, SIGN_IN_PATH } from '@/features/auth/destination'
import { fetchPrincipal } from '@/features/auth/local-session'
import { useT } from '@/i18n/locale-provider'

const schema = z
  .object({
    currentPassword: z.string().min(1, 'Enter your current password'),
    newPassword: z.string().min(10, 'Use at least 10 characters').max(256, 'Use at most 256 characters'),
    confirmPassword: z.string(),
  })
  .refine((values) => values.newPassword === values.confirmPassword, {
    path: ['confirmPassword'],
    message: 'The passwords do not match',
  })
  .refine((values) => values.newPassword !== values.currentPassword, {
    path: ['newPassword'],
    message: 'Choose a different password',
  })

type Values = z.infer<typeof schema>

export function ChangePasswordPage() {
  const t = useT()
  useRouteMeta()
  usePageTitle(t('Change password'))
  const { status, user, provider, changePassword } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: unknown } | null)?.from
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) })

  if (status === 'loading') return <LoadingState label={t('Checking your session…')} className="min-h-dvh" />
  if (!user) return <Navigate to={SIGN_IN_PATH} replace state={{ from: location.pathname }} />

  const forced = Boolean(user.mustChangePassword)
  const supported = provider === 'local' && changePassword

  const onSubmit = handleSubmit(async (values) => {
    if (!changePassword) return
    setFormError(null)
    try {
      await changePassword(values.currentPassword, values.newPassword)
      const refreshed = await fetchPrincipal()
      navigate(destinationFor(refreshed, from), { replace: true })
    } catch (error) {
      setFormError(error instanceof Error ? error.message : t('The password could not be changed.'))
    }
  })

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-surface px-4 py-12">
      <Link to="/" className="mb-8" aria-label={t('VoteTrace home')}>
        <Logo showTagline />
      </Link>
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <KeyRoundIcon className="size-5 text-primary" aria-hidden />
            {forced ? t('Set your own password') : t('Change password')}
          </CardTitle>
          <CardDescription>
            {forced
              ? t('You signed in with a temporary password. Choose your own before continuing.')
              : t('Signing in elsewhere will end once you change it.')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!supported ? (
            <Alert variant="info">
              <AlertTitle>{t('Managed by your identity provider')}</AlertTitle>
              <AlertDescription>{t('Change your password where you manage your Supabase account.')}</AlertDescription>
            </Alert>
          ) : (
            <form onSubmit={onSubmit} noValidate className="space-y-4">
              <FormField
                id="current-password"
                label={forced ? t('Temporary password') : t('Current password')}
                error={errors.currentPassword?.message}
              >
                <Input
                  id="current-password"
                  type="password"
                  autoComplete="current-password"
                  aria-invalid={Boolean(errors.currentPassword)}
                  aria-describedby={describedBy('current-password', errors.currentPassword?.message)}
                  {...register('currentPassword')}
                />
              </FormField>
              <FormField
                id="new-password"
                label={t('New password')}
                hint={t('At least 10 characters. Avoid your name or email.')}
                error={errors.newPassword?.message}
              >
                <Input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  aria-invalid={Boolean(errors.newPassword)}
                  aria-describedby={describedBy('new-password', errors.newPassword?.message)}
                  {...register('newPassword')}
                />
              </FormField>
              <FormField id="confirm-password" label={t('Repeat new password')} error={errors.confirmPassword?.message}>
                <Input
                  id="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  aria-invalid={Boolean(errors.confirmPassword)}
                  aria-describedby={describedBy('confirm-password', errors.confirmPassword?.message)}
                  {...register('confirmPassword')}
                />
              </FormField>
              {formError && (
                <p role="alert" className="text-sm font-medium text-destructive">
                  {formError}
                </p>
              )}
              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting && <Spinner />}
                {t('Save password')}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
      {!forced && (
        <Button asChild variant="link" className="mt-6 text-muted-foreground">
          <Link to={destinationFor(user, from)}>
            <ArrowLeftIcon />
            {t('Back')}
          </Link>
        </Button>
      )}
    </div>
  )
}
