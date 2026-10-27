import { expect, test } from '@playwright/test';

async function login(page: import('@playwright/test').Page, key: string) {
  await page.goto('/login');
  await page.locator('#apiKey').fill(key);
  await page.getByRole('button', { name: 'Accedi' }).click();
}

test('admin creates, rotates and revokes a credential and sees the secret once', async ({ page }) => {
  await login(page, 'admin-key');
  const name = `reporting-bot-${Date.now()}`;

  await page.goto('/credentials');
  await expect(page.getByRole('heading', { name: 'Credenziali', exact: true, level: 1 })).toBeVisible();
  const pageResponse = await page.reload();
  expect(pageResponse?.headers()['cache-control']).toContain('no-store');
  await expect(page.getByText('ci-runner')).toBeVisible();

  await page.getByLabel('Principal ID').fill(name);
  await page.getByLabel('Ruolo').selectOption('reader');
  await page.getByLabel('Scope').fill('assistants:read, models:read');
  await page.getByRole('button', { name: 'Crea credenziale' }).click();

  const secret = page.getByTestId('credential-secret');
  await expect(secret).toBeVisible();
  const firstKey = (await secret.textContent())?.trim() ?? '';
  expect(firstKey).toMatch(/^uai_test_/);

  const row = page.getByRole('row', { name: new RegExp(name) });
  await expect(row).toBeVisible();
  await expect(row.getByText('Attiva')).toBeVisible();

  await row.getByText('Ruota', { exact: true }).click();
  await row.getByRole('button', { name: 'Ruota chiave' }).click();
  await expect(secret).toBeVisible();
  const rotatedKey = (await secret.textContent())?.trim() ?? '';
  expect(rotatedKey).toMatch(/^uai_test_/);
  expect(rotatedKey).not.toBe(firstKey);

  const updatedRow = page.getByRole('row', { name: new RegExp(name) });
  await updatedRow.getByText('Revoca', { exact: true }).click();
  await updatedRow.getByRole('button', { name: 'Conferma revoca' }).click();
  await expect(updatedRow.getByText('Revocata')).toBeVisible();
});

test('readers cannot manage credentials', async ({ page }) => {
  await login(page, 'reader-key');

  await page.goto('/credentials');
  await expect(page.getByText(/riservata agli amministratori/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Crea credenziale' })).toHaveCount(0);
});

test('readers cannot read the audit log', async ({ page }) => {
  await login(page, 'reader-key');

  await page.goto('/audit');
  await expect(page.getByText(/riservata agli amministratori con scope/)).toBeVisible();
  await expect(page.getByLabel('Azione', { exact: true })).toHaveCount(0);
});

test('admin filters audit events by action', async ({ page }) => {
  await login(page, 'admin-key');

  await page.goto('/audit');
  await expect(page.getByText('tool.approved', { exact: true })).toBeVisible();
  await expect(page.getByText('credential.created', { exact: true })).toBeVisible();

  await page.getByLabel('Azione', { exact: true }).fill('credential.created');
  await page.getByRole('button', { name: 'Filtra' }).click();

  await expect(page).toHaveURL(/action=credential\.created/);
  await expect(page.getByText('credential.created', { exact: true })).toHaveCount(1);
  await expect(page.getByText('tool.approved', { exact: true })).toHaveCount(0);
});

test('dashboard shows gateway health', async ({ page }) => {
  await login(page, 'admin-key');

  await expect(page.getByTestId('gateway-status')).toHaveText('Gateway ok');
  await expect(page.getByTestId('gateway-version')).toHaveText('versione vtest');
});
