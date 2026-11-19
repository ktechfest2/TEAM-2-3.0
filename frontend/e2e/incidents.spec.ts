import { expect, test } from '@playwright/test'

/** Runs against the preview build. No API is running, so pages must fail gracefully. */

test('incident form validates before anything is sent', async ({ page }) => {
  await page.goto('/report-incident')
  await expect(page.getByRole('heading', { level: 1, name: 'Report an incident' })).toBeVisible()
  await expect(page.getByText('In danger? Get help first')).toBeVisible()
  await page.getByRole('button', { name: 'Send report' }).click()
  await expect(page.getByText('Select a category', { exact: true }).last()).toBeVisible()
  await expect(page.getByText('Describe what happened in at least 20 characters')).toBeVisible()
})

test('public incident summary explains that reports are not findings', async ({ page }) => {
  await page.goto('/incidents')
  await expect(page.getByRole('heading', { level: 1, name: 'Incident summary' })).toBeVisible()
  await expect(page.getByText('Reports are not findings')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Report an incident' }).first()).toBeVisible()
})

test('phone access page is labelled as a test console without a shortcode', async ({ page }) => {
  await page.goto('/phone-access')
  await expect(page.getByRole('heading', { level: 1, name: 'USSD and SMS access' })).toBeVisible()
  await expect(page.getByText('Test console')).toBeVisible()
  await expect(page.getByText(/No USSD code is shown until one is allocated/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Dial' })).toBeEnabled()
})

test('incident review area requires staff sign-in', async ({ page }) => {
  await page.goto('/admin/incidents')
  await expect(page).toHaveURL(/\/admin\/sign-in$/)
})

test('footer links reach the new public pages', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('contentinfo').getByRole('link', { name: 'USSD and SMS access' }).click()
  await expect(page).toHaveURL(/\/phone-access$/)
  await page.getByRole('contentinfo').getByRole('link', { name: 'Incident summary' }).click()
  await expect(page).toHaveURL(/\/incidents$/)
})
