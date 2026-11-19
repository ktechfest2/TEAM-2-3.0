import { CameraIcon, ClipboardCheckIcon, FileDigitIcon, ShieldCheckIcon, TagIcon } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  VERIFICATION_STATUSES,
  VERIFICATION_STATUS_META,
  VerificationStatusBadge,
} from '@/features/verification/status'
import { useT } from '@/i18n/locale-provider'

export function VerificationInfoPage() {
  const t = useT()
  const process = [
    {
      title: t('Evidence is submitted'),
      body: t('Observers photograph the result sheet. Each file is stored privately with its time and polling unit.'),
      icon: CameraIcon,
    },
    {
      title: t('Figures are recorded'),
      body: t('The vote counts on the sheet are recorded for that polling unit.'),
      icon: FileDigitIcon,
    },
    {
      title: t('A reviewer compares'),
      body: t('The figures are checked against the photo and any other submissions.'),
      icon: ClipboardCheckIcon,
    },
    {
      title: t('A status is assigned'),
      body: t('Only reviewers can set a status. Every decision is logged.'),
      icon: TagIcon,
    },
  ]
  return (
    <div className="mx-auto max-w-5xl space-y-10 px-4 py-10 sm:px-6">
      <PageHeader
        eyebrow={t('Methodology')}
        title={t('How verification works')} description={t('How we check polling-unit figures against evidence from the ground.')}
      />

      <section aria-labelledby="process-heading">
        <h2 id="process-heading" className="text-lg font-semibold">
          {t('The process')}
        </h2>
        <ol className="mt-4 space-y-3">
          {process.map((step, index) => (
            <li key={step.title} className="flex gap-4 rounded-lg border bg-card p-4">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-[5px] bg-primary text-primary-foreground">
                <step.icon className="size-5" strokeWidth={1.75} aria-hidden />
                <span className="sr-only">{t('Step {n}', { n: index + 1 })}</span>
              </span>
              <div>
                <h3 className="font-medium">{step.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="statuses-heading">
        <h2 id="statuses-heading" className="text-lg font-semibold">
          {t('What each status means')}
        </h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {VERIFICATION_STATUSES.map((status) => (
            <Card key={status}>
              <CardHeader className="pb-2">
                <CardTitle>
                  <VerificationStatusBadge status={status} />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{t(VERIFICATION_STATUS_META[status].description)}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <Alert variant="info">
        <ShieldCheckIcon />
        <AlertTitle>{t('VoteTrace does not declare results')}</AlertTitle>
        <AlertDescription>
          {t('Official results come from INEC. VoteTrace is an independent check.')}
        </AlertDescription>
      </Alert>
    </div>
  )
}
