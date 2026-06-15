import { test, expect } from '@playwright/test';
import { PERSONAS, loginAs } from './helpers';

test.describe('Authentication & routing', () => {
  test('login page renders the quick-access personas', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByText('ACCÈS RAPIDE')).toBeVisible();
    await expect(page.getByRole('button', { name: /Nadia Mansour/ })).toBeVisible();
  });

  for (const persona of ['adherent', 'agent', 'admin'] as const) {
    test(`${persona} lands in its zone`, async ({ page }) => {
      await loginAs(page, persona);
      await expect(page).toHaveURL(PERSONAS[persona].url);
    });
  }

  test('logging out returns to /login', async ({ page }) => {
    await loginAs(page, 'adherent');  // chat zone has the labelled logout control
    await page.getByRole('button', { name: /Se déconnecter/ }).first().click();
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
  });
});
