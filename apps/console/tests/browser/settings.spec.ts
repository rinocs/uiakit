import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

async function login(page: import('@playwright/test').Page, key = 'admin-key') {
  await page.goto('/login');
  await page.locator('#apiKey').fill(key);
  await page.getByRole('button', { name: 'Accedi' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
}
async function openAssistant(page: import('@playwright/test').Page) {
  await page.goto('/assistants');
  await page.locator('.list a').first().click();
}

test('appearance persists through navigation and reload, supports system theme and compact density', async ({ page }) => {
  await login(page);
  await page.getByRole('link', { name: 'Impostazioni', exact: true }).first().click();
  await page.locator('#theme').selectOption('light');
  await page.locator('#density').selectOption('compact');
  await page.getByRole('button', { name: 'Salva preferenze' }).click();
  await expect(page.getByRole('status')).toContainText('Preferenze salvate');
  await expect(page.locator('.shell')).toHaveAttribute('data-theme', 'light');
  const light = await page.locator('.shell').evaluate((node) => getComputedStyle(node).backgroundColor);
  await page.goto('/models');
  await page.reload();
  await expect(page.locator('.shell')).toHaveAttribute('data-density', 'compact');
  await expect(page.locator('.shell')).toHaveAttribute('data-theme', 'light');
  await page.goto('/settings');
  await page.locator('#theme').selectOption('system');
  await page.getByRole('button', { name: 'Salva preferenze' }).click();
  await page.emulateMedia({ colorScheme: 'light' });
  expect(await page.locator('.shell').evaluate((node) => getComputedStyle(node).backgroundColor)).toBe(light);
  await page.emulateMedia({ colorScheme: 'dark' });
  expect(await page.locator('.shell').evaluate((node) => getComputedStyle(node).backgroundColor)).not.toBe(light);
});

test('operational settings survive versioned save; rejected updates retain entered values', async ({ page, context }) => {
  await login(page);
  await openAssistant(page);
  await page.locator('#description').fill('Configurazione operativa di prova');
  await page.locator('#tools').selectOption(['example.lookup']);
  await page.locator('#knowledge_base_ids').selectOption(['00000000-0000-4000-8000-0000000000b1']);
  await page.locator('[name="conversation"]').uncheck();
  await page.locator('#max_tokens').fill('2048');
  await page.locator('#max_steps').fill('0');
  await page.getByRole('button', { name: 'Salva nuova versione' }).click();
  await expect(page.locator('#description')).toHaveValue('Configurazione operativa di prova');
  await expect(page.locator('#tools')).toHaveValues(['example.lookup']);
  await expect(page.locator('#knowledge_base_ids')).toHaveValues(['00000000-0000-4000-8000-0000000000b1']);
  await expect(page.locator('[name="conversation"]')).not.toBeChecked();
  await expect(page.locator('#max_tokens')).toHaveValue('2048');
  await page.reload();
  await expect(page.locator('#max_steps')).toHaveValue('0');
  const second = await context.newPage();
  await second.goto(page.url());
  await second.locator('#description').fill('Modifica concorrente');
  await second.getByRole('button', { name: 'Salva nuova versione' }).click();
  await page.locator('#description').fill('Modifica da recuperare');
  await page.getByRole('button', { name: 'Salva nuova versione' }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.locator('#description')).toHaveValue('Modifica da recuperare');
  await expect(page.locator('#tools')).toHaveValues(['example.lookup']);
  await second.close();
});

test('reader cannot edit operational settings or forge an update', async ({ page }) => {
  await login(page, 'reader-key');
  await openAssistant(page);
  await expect(page.locator('#max_tokens')).toBeDisabled();
  await expect(page.locator('#tools')).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Salva nuova versione' })).toHaveCount(0);
  const response = await page.request.post(`${page.url()}?/update`, { form: { name: 'Forged', model: 'test-model' } });
  expect(response.status()).toBe(403);
});

test('new settings surfaces are accessible in both themes and fit desktop and mobile', async ({ page }, testInfo) => {
  await login(page);
  for (const theme of ['dark', 'light']) {
    await page.goto('/settings');
    await page.locator('#theme').selectOption(theme);
    await page.getByRole('button', { name: 'Salva preferenze' }).click();
    for (const route of ['/settings', '/assistants']) {
      if (route === '/assistants') await openAssistant(page); else await page.goto(route);
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([]);
    }
  }
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    for (const route of ['/', '/settings', '/assistants', '/models']) {
      if (route === '/assistants') await openAssistant(page); else await page.goto(route);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      const overflowing = overflow ? await page.locator('body *').evaluateAll((nodes) => nodes.filter((node) => node.getBoundingClientRect().right > innerWidth).slice(0, 12).map((node) => ({ tag: node.tagName, class: String(node.className), width: node.getBoundingClientRect().width }))) : [];
      expect(overflow, JSON.stringify(overflowing)).toBe(false);
      await page.screenshot({ path: testInfo.outputPath(`${viewport.width}-${route.replaceAll('/', '') || 'dashboard'}.png`), fullPage: true });
    }
  }
});
