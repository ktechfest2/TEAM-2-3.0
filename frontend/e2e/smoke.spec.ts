import { expect, test } from '@playwright/test'

test('home page renders the brand and primary navigation', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveTitle(/VoteTrace/)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByRole('link', { name: 'VoteTrace home' })).toBeVisible()
})

test('admin area requires sign-in', async ({ page }) => {
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/admin\/sign-in$/)
  await expect(page.getByLabel('Password')).toBeVisible()
})

test('mobile menu exposes every public section', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'mobile only')
  await page.goto('/')
  await page.getByRole('button', { name: 'More' }).click()
  const menu = page.getByRole('navigation', { name: 'Mobile' })
  for (const label of ['Find polling unit', 'Results', 'How verification works', 'Updates', 'Report an incident']) {
    await expect(menu.getByRole('link', { name: label })).toBeVisible()
  }
})
