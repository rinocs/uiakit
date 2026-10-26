import { expect, test } from '@playwright/test';

const PUBLIC_KB = '00000000-0000-4000-8000-0000000000b1';
const PRIVATE_KB = '00000000-0000-4000-8000-0000000000b2';

async function login(page: import('@playwright/test').Page, key: string) {
  await page.goto('/login');
  await page.locator('#apiKey').fill(key);
  await page.getByRole('button', { name: 'Accedi' }).click();
}

test('admin uploads a document, polls ingestion, associates an assistant and opens the authorized source', async ({ page }) => {
  await login(page, 'admin-key');
  await page.getByRole('link', { name: 'Knowledge base', exact: true }).click();
  await expect(page.getByText('Supporto clienti')).toBeVisible();
  await page.getByRole('link', { name: /Supporto clienti/ }).click();

  await expect(page.getByText(/Limite 20 MiB/)).toBeVisible();
  const assistantCheckbox = page.getByRole('checkbox').first();
  if (!(await assistantCheckbox.isChecked())) {
    await assistantCheckbox.check();
    await page.getByRole('button', { name: 'Aggiorna associazioni' }).click();
    await expect(page.getByRole('checkbox').first()).toBeChecked();
  }

  await page.locator('#file').setInputFiles({
    name: 'note.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('Contenuto fonte di prova'),
  });
  await page.locator('#title').fill('Nota test');
  await page.getByRole('button', { name: 'Carica e accoda' }).click();

  await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${PUBLIC_KB}\\?uploaded=`));
  await expect(page.getByRole('link', { name: 'Nota test' })).toBeVisible();
  for (let attempt = 0; attempt < 4; attempt += 1) {
    if (await page.locator('.document-list').getByText('completed', { exact: true }).count()) break;
    await page.getByRole('link', { name: 'Aggiorna stato' }).click();
    await page.waitForLoadState('networkidle');
  }
  await expect(page.locator('.document-list').getByText('completed', { exact: true })).toBeVisible();
  await expect(page.locator('.document-list > li')).toHaveCount(1);

  await page.getByRole('link', { name: 'Apri fonte' }).click();
  await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${PUBLIC_KB}/documents/`));
  await expect(page.getByRole('heading', { name: 'Nota test' })).toBeVisible();
  await expect(page.getByText('Contenuto fonte di prova')).toBeVisible();

  await page.getByRole('link', { name: 'Torna alla knowledge base' }).click();
  await expect(page.getByText(/pagina 1 · offset/)).not.toBeVisible();
});

test('reader only sees authorized knowledge bases and cannot upload', async ({ page }) => {
  await login(page, 'reader-key');
  await page.getByRole('link', { name: 'Knowledge base', exact: true }).click();
  await expect(page.getByText('Supporto clienti')).toBeVisible();
  await expect(page.getByText('Riservato', { exact: true })).toHaveCount(0);

  await page.getByRole('link', { name: /Supporto clienti/ }).click();
  await expect(page.getByText('Ruolo reader: knowledge base in sola lettura.')).toBeVisible();
  await expect(page.locator('#file')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Carica e accoda' })).toHaveCount(0);

  const response = await page.goto(`/knowledge-bases/${PRIVATE_KB}`);
  expect(response?.status()).toBe(404);
});
