import { test, expect } from '@playwright/test';
import { loginAs } from './helpers';

test.describe('Admin zone', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'admin');
  });

  test('dashboard shows the overview + KPI cards', async ({ page }) => {
    await expect(page).toHaveURL(/\/admin\/dashboard/);
    await expect(page.getByText('Support Overview')).toBeVisible();
    await expect(page.getByText('Total Requests')).toBeVisible();
    await expect(page.getByText('System Health')).toBeVisible();
  });

  test('KPI drill-down navigates to a filtered Logs view', async ({ page }) => {
    await page.getByText('RAG Resolved', { exact: false }).first().click();
    await expect(page).toHaveURL(/\/admin\/logs\?outcome=RAG_RESOLVED/);
    // The Outcome filter reflects the drill-down.
    await expect(page.locator('select')).toHaveValue('RAG_RESOLVED');
  });

  test('Knowledge curation page renders', async ({ page }) => {
    await page.goto('/admin/knowledge');
    await expect(page.getByText('Knowledge Base').first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Entries' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Corrections' })).toBeVisible();
  });

  test('Logs table timestamps are humanised (no raw ISO)', async ({ page }) => {
    await page.goto('/admin/logs');
    await expect(page.getByText('Logs & Audit Trail')).toBeVisible();
    // No raw "...T..:..:...microseconds+00:00" left in the table.
    await expect(page.locator('body')).not.toContainText(/\dT\d{2}:\d{2}:\d{2}\.\d/);
  });
});
