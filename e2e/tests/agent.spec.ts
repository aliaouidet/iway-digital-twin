import { test, expect } from '@playwright/test';
import { loginAs } from './helpers';

test.describe('Agent workspace', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'agent');
  });

  test('queue + filters load', async ({ page }) => {
    await expect(page).toHaveURL(/\/agent/);
    // Queue filter tabs (Tout / Urgent / Actif / Mes cas).
    await expect(page.getByText(/Tout/).first()).toBeVisible();
    await expect(page.getByText(/Urgent/).first()).toBeVisible();
  });

  test('opening a session reveals the client dossier action', async ({ page }) => {
    const firstCase = page.getByText(/msgs/).first();
    if (await firstCase.count()) {
      await firstCase.click();
      // The workspace exposes the dossier / take-over actions for a selected case.
      await expect(page.getByRole('button', { name: /Dossier client|Prendre en charge/ }).first())
        .toBeVisible({ timeout: 15_000 });
    } else {
      test.skip(true, 'empty queue — no case to open');
    }
  });
});
