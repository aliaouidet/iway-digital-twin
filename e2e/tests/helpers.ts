import { Page, expect } from '@playwright/test';

/**
 * One-click demo login via the "Accès rapide" persona buttons on /login.
 * Each persona lands in its zone (adherent → /chat, agent → /agent, admin → /admin).
 */
export const PERSONAS = {
  adherent: { name: 'Nadia Mansour', url: /\/chat/ },
  prestataire: { name: 'Dr. Amine Zaid', url: /\/chat/ },
  agent: { name: 'Karim Belhadj', url: /\/agent/ },
  admin: { name: 'Sara Toumi', url: /\/admin/ },
} as const;

export async function loginAs(page: Page, persona: keyof typeof PERSONAS) {
  const p = PERSONAS[persona];
  await page.goto('/login');
  await page.getByRole('button', { name: new RegExp(p.name) }).click();
  await expect(page).toHaveURL(p.url, { timeout: 20_000 });
}
