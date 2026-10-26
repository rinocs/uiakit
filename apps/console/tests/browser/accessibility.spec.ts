import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

async function seriousViolations(page: import('@playwright/test').Page) {
  const results = await new AxeBuilder({ page }).analyze();
  return results.violations.filter((violation) =>
    ['serious', 'critical'].includes(violation.impact ?? ''),
  );
}

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.locator('#apiKey').fill('admin-key');
  await page.getByRole('button', { name: 'Accedi' }).click();
}

test('console pages have no serious accessibility violations and hardened browser headers', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  const loginResponse = await page.goto('/login');
  expect(loginResponse?.headers()['x-frame-options']).toBe('DENY');
  expect(loginResponse?.headers()['x-content-type-options']).toBe('nosniff');
  const csp = loginResponse?.headers()['content-security-policy'] ?? '';
  expect(csp).toMatch(/script-src 'self' 'sha256-/);
  expect(csp).not.toMatch(/script-src 'self' 'unsafe-inline'/);

  expect(await seriousViolations(page)).toEqual([]);
  await login(page);
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  expect(await seriousViolations(page)).toEqual([]);

  await page.getByRole('link', { name: 'Assistenti', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Assistenti' })).toBeVisible();
  expect(await seriousViolations(page)).toEqual([]);

  const exposed = await page.evaluate(() => ({
    html: document.documentElement.outerHTML,
    local: JSON.stringify(localStorage),
    session: JSON.stringify(sessionStorage),
    cookies: document.cookie,
  }));
  expect(JSON.stringify(exposed)).not.toContain('admin-key');
  expect(pageErrors).toEqual([]);
});
