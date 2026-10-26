import { expect, test } from '@playwright/test';

async function login(page: import('@playwright/test').Page, key: string) {
  await page.goto('/login');
  await page.locator('#apiKey').fill(key);
  await page.getByRole('button', { name: 'Accedi' }).click();
}

test('runs show terminal states, usage is shown in the playground, and audit details are redacted', async ({ page }) => {
  await login(page, 'admin-key');
  await page.goto('/runs');
  await expect(page.getByText('completed', { exact: true })).toBeVisible();
  await expect(page.getByText('waiting_approval', { exact: true })).toBeVisible();
  await expect(page.getByText('failed', { exact: true })).toBeVisible();
  await expect(page.getByText('cancelled', { exact: true })).toBeVisible();

  await page.goto('/runs/00000000-0000-4000-8000-000000000102');
  await expect(page.getByText('waiting_approval', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: /example\.write/ })).toBeVisible();
  await expect(page.getByText('Audit', { exact: true })).toBeVisible();
  await expect(page.getByText('[redacted]', { exact: false })).toBeVisible();
  await expect(page.getByText('super-secret', { exact: false })).toHaveCount(0);

  await page.goto('/playground?conversation=00000000-0000-4000-8000-0000000000c9');
  await page.locator('#playground-input').fill('Ciao');
  await page.getByRole('button', { name: 'Invia' }).click();
  await expect(page.getByText('Completato', { exact: true })).toBeVisible();
  await expect(page.getByText('Usage: input 3 / output 4')).toBeVisible();
  const citation = page.getByRole('link', { name: /Fonte/ }).last();
  await expect(citation).toHaveAttribute('href', /knowledge-bases\/00000000-0000-4000-8000-0000000000b1\/documents\//);
});

test('duplicate SSE events do not duplicate text', async ({ page }) => {
  await login(page, 'admin-key');
  await page.goto('/playground?conversation=00000000-0000-4000-8000-0000000000c5');
  await page.locator('#playground-input').fill('Ciao');
  await page.getByRole('button', { name: 'Invia' }).click();
  await expect(page.getByText('Completato', { exact: true })).toBeVisible();
  const text = await page.locator('.playground-messages article[data-role="assistant"] .message-text').last().textContent();
  expect(text?.trim()).toBe('Ciao');
});

test('interrupted stream is not success and replay completes with the same idempotency key', async ({ page }) => {
  await login(page, 'admin-key');
  await page.goto('/playground?conversation=00000000-0000-4000-8000-0000000000c7');
  await page.locator('#playground-input').fill('Riprova');
  await page.getByRole('button', { name: 'Invia' }).click();
  await expect(page.getByText(/incompleta/i).first()).toBeVisible();
  await page.getByRole('button', { name: 'Riprova con la stessa richiesta' }).click();
  await expect(page.getByText('Completato', { exact: true })).toBeVisible();
  await expect(page.locator('.playground-messages article[data-role="assistant"] .message-text').last()).toHaveText('Risposta completa');
});

test('cancel aborts the stream and does not show success', async ({ page }) => {
  await login(page, 'admin-key');
  await page.goto('/playground?conversation=00000000-0000-4000-8000-0000000000c8');
  await page.locator('#playground-input').fill('Attendi');
  await page.getByRole('button', { name: 'Invia' }).click();
  await expect(page.getByText('Attendo…', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Annulla' }).click();
  await expect(page.getByText(/annullata/i).first()).toBeVisible();
  await expect(page.getByText('Completato', { exact: true })).toHaveCount(0);
});
