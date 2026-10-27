import { expect, test } from '@playwright/test';

async function login(page: import('@playwright/test').Page, key: string) {
  await page.goto('/login');
  await page.locator('#apiKey').fill(key);
  await page.getByRole('button', { name: 'Accedi' }).click();
}

test('admin configures the provider and manages the model catalog', async ({ page }) => {
  await login(page, 'admin-key');

  await page.goto('/provider');
  await expect(page.getByRole('heading', { name: 'Provider', exact: true, level: 1 })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'test-model', exact: true })).toBeVisible();

  await page.getByLabel('Base URL').fill('http://provider.local/v2');
  await page.getByLabel('Max output tokens · 1–8192').fill('2048');
  await page.getByRole('button', { name: 'Salva provider' }).click();
  await expect(page.getByText('Configurazione provider salvata.')).toBeVisible();
  await expect(page.getByLabel('Base URL')).toHaveValue('http://provider.local/v2');

  await page.getByRole('button', { name: 'Scopri modelli dal provider' }).click();
  const discovery = page.getByText('Modelli esposti dal provider').locator('..');
  await expect(discovery).toContainText('extra-model');

  const id = `catalog-model-${Date.now()}`;
  await page.getByLabel('Identificativo modello').fill(id);
  await page.getByLabel('Finestra di contesto').fill('4096');
  await page.getByRole('button', { name: 'Aggiungi modello' }).click();
  await expect(page.getByRole('cell', { name: id, exact: true })).toBeVisible();

  await page.goto('/models');
  await expect(page.getByRole('cell', { name: id, exact: true })).toBeVisible();

  await page.goto('/provider');
  const row = page.getByRole('row', { name: new RegExp(id) });
  await row.getByRole('button', { name: 'Rimuovi' }).click();
  await expect(page.getByRole('cell', { name: id, exact: true })).toHaveCount(0);
});

test('readers cannot manage the provider', async ({ page }) => {
  await login(page, 'reader-key');

  await page.goto('/provider');
  await expect(page.getByText(/riservata agli amministratori con gli scope/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Salva provider' })).toHaveCount(0);
});
