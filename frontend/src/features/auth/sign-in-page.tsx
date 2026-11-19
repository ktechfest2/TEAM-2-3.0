import { zodResolver } from '@hookform/resolvers/zod'
import { AlertTriangleIcon, ArrowLeftIcon, EyeIcon, EyeOffIcon } from 'lucide-react'
import { type KeyboardEvent, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'
import { z } from 'zod'
import { usePageTitle, useRouteMeta } from '@/app/seo'
import { Logo } from '@/components/brand/logo'
import { describedBy, FormField } from '@/components/forms/form-field'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { useAuth } from '@/features/auth/auth-context'
import { destinationFor } from '@/features/auth/destination'
import { ADMIN_CONSOLE_ROLES, hasAnyRole } from '@/features/auth/roles'
import { useT } from '@/i18n/locale-provider'

const signInSchema = z.object({
  email: z.email('Enter a valid email address'),
  password: z.string().min(1, 'Enter your password'),
})

type SignInValues = z.infer<typeof signInSchema>

export function SignInPage() {
  const t = useT()
  useRouteMeta()
  usePageTitle(t('Sign in'))
  const { status, user, isConfigured, isPreview, signInWithPassword } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [formError, setFormError] = useState<string | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [capsLock, setCapsLock] = useState(false)
  const from = (location.state as { from?: unknown } | null)?.from

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignInValues>({ resolver: zodResolver(signInSchema) })

  // Staff go straight to their area. Other signed-in accounts stay on this form
  // so they can sign in with a staff email and password.
  if (status === 'authenticated' && user && !isPreview && (user.mustChangePassword || hasAnyRole(user.roles, ADMIN_CONSOLE_ROLES))) {
    return <Navigate to={destinationFor(user, from)} replace state={{ from }} />
  }

  const onSubmit = handleSubmit(async ({ email, password }) => {
    setFormError(null)
    try {
      const signedIn = await signInWithPassword(email, password)
      navigate(destinationFor(signedIn, from), { replace: true, state: { from } })
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Sign-in failed.')
    }
  })

  const trackCapsLock = (event: KeyboardEvent<HTMLInputElement>) => {
    setCapsLock(event.getModifierState('CapsLock'))
  }

  return (
    <div className="flex min-h-dvh flex-col bg-surface">
      <header className="flex items-center justify-between gap-3 px-4 py-4 sm:px-8">
        <Link to="/" aria-label={t('VoteTrace home')} className="min-w-0">
          <Logo />
        </Link>
        <Button asChild variant="ghost" size="sm" className="shrink-0 px-2 text-muted-foreground sm:px-3">
          <Link to="/">
            <ArrowLeftIcon />
            <span className="max-sm:sr-only">{t('Back to public site')}</span>
          </Link>
        </Button>
      </header>

      <main className="flex flex-1 items-start justify-center px-5 pt-8 pb-16 sm:pt-16">
        <div className="w-full max-w-sm rounded-md border border-border bg-card p-6 shadow-sm sm:p-8">
          <h1 className="text-2xl font-bold tracking-tight text-navy">{t('Sign in')}</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {t('Use the email and password your administrator gave you.')}
          </p>

          {!isConfigured && (
            <Alert variant="warning" className="mt-6">
              <AlertTriangleIcon />
              <AlertTitle>{t('Authentication not configured')}</AlertTitle>
              <AlertDescription>{t('Sign-in is not available in this environment.')}</AlertDescription>
            </Alert>
          )}

          <form onSubmit={onSubmit} noValidate className="mt-6 space-y-5">
            <FormField id="email" label={t('Email')} error={errors.email?.message}>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                className="h-11"
                aria-invalid={Boolean(errors.email)}
                aria-describedby={describedBy('email', errors.email?.message)}
                {...register('email')}
              />
            </FormField>

            <FormField id="password" label={t('Password')} error={errors.password?.message}>
              <div className="relative">
                <Input
                  id="password"
                  type={revealed ? 'text' : 'password'}
                  autoComplete="current-password"
                  className="h-11 pr-11"
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={describedBy('password', errors.password?.message)}
                  onKeyUp={trackCapsLock}
                  onKeyDown={trackCapsLock}
                  {...register('password')}
                />
                <button
                  type="button"
                  onClick={() => setRevealed((value) => !value)}
                  aria-pressed={revealed}
                  aria-controls="password"
                  className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-md text-muted-foreground hover:text-navy focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {revealed ? <EyeOffIcon className="size-4" aria-hidden /> : <EyeIcon className="size-4" aria-hidden />}
                  <span className="sr-only">{revealed ? t('Hide password') : t('Show password')}</span>
                </button>
              </div>
              {capsLock && <p className="mt-1.5 text-xs font-medium text-warning">{t('Caps Lock is on.')}</p>}
            </FormField>

            {formError && (
              <Alert variant="destructive" role="alert">
                <AlertTriangleIcon />
                <AlertDescription>{formError}</AlertDescription>
              </Alert>
            )}

            <Button type="submit" className="h-11 w-full" disabled={isSubmitting || !isConfigured}>
              {isSubmitting && <Spinner />}
              {t('Sign in')}
            </Button>
          </form>

          <p className="mt-6 text-xs text-muted-foreground">
            {t('Forgotten your password? Ask your system administrator to reset it.')}
          </p>
        </div>
      </main>
    </div>
  )
}
