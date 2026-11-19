# Design system

The aim is a calm, institutional, trustworthy interface: clear hierarchy, generous but consistent
spacing, restrained colour, and no decorative noise.

## Tokens

Defined as CSS variables in `frontend/src/styles/index.css` and exposed as Tailwind 4 utilities
(`bg-primary`, `text-muted-foreground`, `border-border`, …). Names follow the shadcn/ui
convention, so components generated with `npx shadcn add …` work without changes.

| Token | Value | Use |
| --- | --- | --- |
| `navy` | `#011b33` | Headings, body, dark sections (Paystack midnight) |
| `primary` | `#3bb75e` | Primary buttons, white text (Paystack live CTA) |
| `cerulean` | `#0ba4db` | Secondary accent on the live site |
| `sky` | `#00c3f7` | Stack/logo cyan, used in the mark |
| `secondary` | `#011b33` navy | Secondary actions |
| `accent` | `#e6f9fe` | Hover and active backgrounds |
| `background` / `surface` | `#ffffff` / `#f5f7fa` | Page and section backgrounds |
| `foreground` | `#011b33` | Body text |
| `muted-foreground` | `#3d5166` | Secondary text |
| `success` | `#15803d` | Verified and positive states |
| `warning` | `#b45309` amber | Discrepancies, offline notices |
| `destructive` | `#b42318` restrained red | Errors, rejection |
| `info` | `#1d4ed8` | Informational notices |

Each status colour has a `*-subtle` background for badges and alerts. All text and background
pairs meet WCAG 2.1 AA. The radius is 0.5rem, so cards are rounded without looking playful.

Typography: Inter (self-hosted variable font, which also works offline) with the Latin,
Latin Extended and combining-diacritic subsets needed for English, Hausa, Igbo and Yoruba.

## Components

| Path | Components |
| --- | --- |
| `components/ui` | `Button` (default, secondary, outline, ghost, subtle, destructive, link), `Card`, `Badge`, `Input`, `Textarea`, `Select`, `Label`, `Alert`, `Skeleton`, `Separator`, `Sheet`, `Spinner` |
| `components/feedback` | `LoadingState` (spinner or skeleton), `ErrorState` (with retry), `EmptyState` |
| `components/layout` | `PageHeader`, `PlannedModule`, `OfflineBanner`, `RouteProgress` |
| `components/forms` | `FormField` + `describedBy()` for accessible labels, hints and errors |
| `features/verification/status.tsx` | `VerificationStatusBadge` and the shared status vocabulary |

## Conventions

- **No fabricated data.** Unbuilt modules use `EmptyState` and `PlannedModule`, never placeholder numbers.
- **Accessibility.** Skip link, visible focus rings, labelled navigation landmarks, `aria-invalid`
  and `aria-describedby` on form fields, and reduced-motion support.
- **Responsive.** The mobile-first public header collapses into a slide-over menu below `lg`. The
  admin sidebar is fixed on desktop and becomes a sheet on tablet and mobile.
- **Motion.** Limited to colour transitions and loading indicators.
