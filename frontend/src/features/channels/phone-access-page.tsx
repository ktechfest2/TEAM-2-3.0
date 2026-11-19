import { MessageSquareTextIcon, PhoneIcon, PhoneOffIcon, SendIcon, SmartphoneIcon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { usePollingUnitSearch } from '@/features/directory/api'
import { sendSms, sendUssdInput, startUssdSession, type SmsReply, type UssdReply } from '@/features/channels/api'
import { useT } from '@/i18n/locale-provider'
import { ApiError } from '@/lib/api-client'
import { useOnlineStatus } from '@/lib/offline/use-online-status'

const SIMULATED_NUMBER = '+2340000000000'

const SMS_COMMANDS: { command: string; help: string }[] = [
  { command: 'RESULT <polling-unit code>', help: 'Reported and verified result for one polling unit' },
  { command: 'STATUS <polling-unit code>', help: 'Location status and verification progress' },
  { command: 'WARD <code>', help: 'Ward totals and coverage' },
  { command: 'LGA <code>', help: 'LGA totals and coverage' },
  { command: 'STATE <code>', help: 'State totals and coverage' },
  { command: 'NATIONAL', help: 'National totals and coverage' },
  { command: 'UPDATES', help: 'Latest election updates' },
  { command: 'MORE', help: 'Next part of a long reply' },
  { command: 'HELP', help: 'List of commands' },
]

function describeError(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.code === 'simulator_disabled' || error.code === 'channel_unavailable' || error.status === 401) {
      return 'The simulator is turned off on this deployment.'
    }
    return error.message
  }
  return fallback
}

function UssdSimulator() {
  const t = useT()
  const online = useOnlineStatus()
  const [session, setSession] = useState<UssdReply | null>(null)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()

  async function dial() {
    setBusy(true)
    setError(undefined)
    try {
      setSession(await startUssdSession())
      setInput('')
    } catch (caught) {
      setError(t(describeError(caught, 'Could not start a session.')))
    } finally {
      setBusy(false)
    }
  }

  async function send(event: FormEvent) {
    event.preventDefault()
    if (!session || session.end || !input.trim()) return
    setBusy(true)
    setError(undefined)
    try {
      setSession(await sendUssdInput(session.session_id, input.trim()))
      setInput('')
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'session_not_found') {
        setSession({ ...session, text: t('Session ended. Dial again.'), end: true })
      } else {
        setError(t(describeError(caught, 'The reply could not be fetched.')))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <SmartphoneIcon className="size-4" aria-hidden />
          {t('USSD simulator')}
        </CardTitle>
        <CardDescription>
          {t('Works like dialling a USSD code on a basic phone. Type the number of a menu option and press Send.')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="mx-auto max-w-xs rounded-[1.75rem] border-4 border-navy bg-navy p-3">
          <div
            className="min-h-56 whitespace-pre-wrap rounded-xl bg-[#e8f0e0] p-3 font-mono text-[13px] leading-snug text-black"
            aria-live="polite"
            data-testid="ussd-screen"
          >
            {session ? session.text : t('Press Dial to start a session.')}
          </div>
          <form onSubmit={send} className="mt-3 flex gap-2">
            <Input
              aria-label={t('USSD reply')}
              value={input}
              maxLength={40}
              inputMode="numeric"
              autoComplete="off"
              disabled={!session || session.end || busy}
              onChange={(event) => setInput(event.target.value)}
              className="bg-white"
            />
            <Button type="submit" disabled={!session || session.end || busy || !input.trim()}>
              {busy ? <Spinner /> : <SendIcon />}
              {t('Send')}
            </Button>
          </form>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button onClick={() => void dial()} disabled={busy || !online} variant={session && !session.end ? 'outline' : 'default'}>
            <PhoneIcon />
            {session && !session.end ? t('Dial again') : t('Dial')}
          </Button>
          {session && !session.end && (
            <Button variant="ghost" onClick={() => setSession(null)}>
              <PhoneOffIcon />
              {t('Hang up')}
            </Button>
          )}
        </div>
        {!online && <p className="text-center text-sm text-muted-foreground">{t('You are offline. The simulator needs a connection.')}</p>}
        {error && (
          <p role="alert" className="text-center text-sm text-destructive">
            {error}
          </p>
        )}
        {session && (
          <p className="text-center text-xs text-muted-foreground">
            {t('{election}. Sessions end after {seconds} seconds without input. 98 shows more, 0 goes back, 00 returns to the menu.', {
              election: session.election,
              seconds: session.timeout_seconds,
            })}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

type SmsExchange = { id: number; text: string; reply?: SmsReply; error?: string }

/** A real code from the register, so example commands work against the live directory. */
function useExampleCode() {
  const units = usePollingUnitSearch({}, true)
  return units.data?.data.items[0]?.code
}

function SmsSimulator() {
  const t = useT()
  const online = useOnlineStatus()
  const exampleCode = useExampleCode()
  const examples = exampleCode
    ? ['HELP', 'NATIONAL', `RESULT ${exampleCode}`, `STATUS ${exampleCode}`, 'UPDATES', 'MORE']
    : ['HELP', 'NATIONAL', 'UPDATES', 'MORE']
  const [text, setText] = useState('')
  const [log, setLog] = useState<SmsExchange[]>([])
  const [busy, setBusy] = useState(false)

  async function send(message: string) {
    const body = message.trim()
    if (!body) return
    const id = Date.now()
    setLog((entries) => [{ id, text: body }, ...entries].slice(0, 20))
    setText('')
    setBusy(true)
    try {
      const reply = await sendSms(SIMULATED_NUMBER, body)
      setLog((entries) => entries.map((entry) => (entry.id === id ? { ...entry, reply } : entry)))
    } catch (caught) {
      const error = t(describeError(caught, 'The message could not be processed.'))
      setLog((entries) => entries.map((entry) => (entry.id === id ? { ...entry, error } : entry)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MessageSquareTextIcon className="size-4" aria-hidden />
          {t('SMS simulator')}
        </CardTitle>
        <CardDescription>
          {t('Type a command as you would in a text message. Long replies arrive in numbered parts of up to 160 characters.')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          onSubmit={(event) => {
            event.preventDefault()
            void send(text)
          }}
          className="flex gap-2"
        >
          <Input
            aria-label={t('SMS message')}
            placeholder={exampleCode ? `RESULT ${exampleCode}` : 'HELP'}
            value={text}
            maxLength={160}
            autoComplete="off"
            onChange={(event) => setText(event.target.value)}
          />
          <Button type="submit" disabled={busy || !text.trim() || !online}>
            {busy ? <Spinner /> : <SendIcon />}
            {t('Send')}
          </Button>
        </form>
        <div className="flex flex-wrap gap-1.5" aria-label={t('Example commands')}>
          {examples.map((command) => (
            <Button key={command} type="button" variant="outline" size="sm" disabled={busy || !online} onClick={() => void send(command)}>
              {command}
            </Button>
          ))}
        </div>
        {!online && <p className="text-sm text-muted-foreground">{t('You are offline. The simulator needs a connection.')}</p>}
        {log.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('Messages and replies appear here.')}</p>
        ) : (
          <ol className="space-y-3" aria-label={t('Conversation')} aria-live="polite">
            {log.map((entry) => (
              <li key={entry.id} className="space-y-1.5">
                <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-primary px-3 py-1.5 font-mono text-xs text-primary-foreground">
                  {entry.text}
                </p>
                {entry.error && <p className="text-xs text-destructive">{entry.error}</p>}
                {entry.reply && (
                  <div className="max-w-[85%] space-y-1">
                    {entry.reply.parts.map((part, index) => (
                      <p key={index} className="rounded-lg bg-muted px-3 py-1.5 font-mono text-xs whitespace-pre-wrap">
                        {part}
                      </p>
                    ))}
                    <p className="text-[11px] text-muted-foreground">
                      {entry.reply.message_ref}
                      {entry.reply.outcome !== 'ok' && (
                        <Badge variant={entry.reply.outcome === 'rate_limited' ? 'warning' : 'neutral'} className="ml-2">
                          {entry.reply.outcome.replace('_', ' ')}
                        </Badge>
                      )}
                    </p>
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}

export function PhoneAccessPage() {
  const t = useT()
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-10 sm:px-6">
      <PageHeader
        eyebrow={t('Basic phone access')}
        title={t('USSD and SMS access')}
        description={t('Results and election updates on any phone, without data.')}
      />
      <Alert variant="warning">
        <PhoneIcon />
        <AlertTitle>{t('Test console')}</AlertTitle>
        <AlertDescription>
          {t('These consoles use the same handlers as real phones. No USSD code is shown until one is allocated.')}
        </AlertDescription>
      </Alert>
      <div className="grid gap-6 lg:grid-cols-2">
        <UssdSimulator />
        <SmsSimulator />
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('SMS commands')}</CardTitle>
          <CardDescription>
            {t('Not case sensitive. Phone channels are read only.')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {SMS_COMMANDS.map((item) => (
              <div key={item.command} className="flex flex-col">
                <dt className="font-mono text-xs font-medium">{item.command}</dt>
                <dd className="text-xs text-muted-foreground">{t(item.help)}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
    </div>
  )
}
