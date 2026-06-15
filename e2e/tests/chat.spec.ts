import { test, expect } from '@playwright/test';
import { loginAs } from './helpers';

// These exercise the live LangGraph + LLM, so they allow a generous timeout.
test.describe('Adherent chat', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'adherent');
  });

  test('new conversation composer is available', async ({ page }) => {
    await expect(page.getByPlaceholder('Écrivez votre message...')).toBeVisible();
  });

  test('sending a personal query returns a beneficiaries answer/card', async ({ page }) => {
    const composer = page.getByPlaceholder('Écrivez votre message...');
    await composer.click();
    await composer.fill('mes bénéficiaires');
    await composer.press('Enter');
    // The user message echoes immediately; the AI reply arrives within ~40s.
    await expect(page.getByText('mes bénéficiaires').first()).toBeVisible();
    await expect(page.getByText(/bénéficiaires/i).nth(1)).toBeVisible({ timeout: 45_000 });
  });

  test('"Parler à un agent" triggers the handoff banner', async ({ page }) => {
    const composer = page.getByPlaceholder('Écrivez votre message...');
    await composer.fill('je veux parler à un agent');
    await composer.press('Enter');
    await expect(page.getByText(/agent.*rejoindre|conseiller/i).first())
      .toBeVisible({ timeout: 45_000 });
  });
});
