import { test, expect } from '@playwright/test';
test('REQ-OWN-LAB own synthetic result displayed', async ({ page }) => {
  await page.goto('/'); await page.getByRole('button', { name:'Load result' }).click();
  await expect(page.getByRole('status')).toContainText('"value":90');
});
test('REQ-ISOLATION browser receives server-side forbidden', async ({ page }) => {
  await page.goto('/'); await page.getByLabel('Lab ID').fill('lab-b');
  const response = page.waitForResponse(r => r.url().endsWith('/api/labs/lab-b'));
  await page.getByRole('button', { name:'Load result' }).click();
  expect((await response).status()).toBe(403); await expect(page.getByRole('status')).toHaveText('Access denied: 403');
});
test('FAULT-UI-001 injected service failure is not shown as lab data', async ({ page }) => {
  // Client fault injection is NOT evidence of server authorization.
  await page.route('**/api/labs/*', route => route.fulfill({ status:503, contentType:'application/json', body:JSON.stringify({ error:'synthetic_unavailable' }) }));
  await page.goto('/'); await page.getByRole('button', { name:'Load result' }).click();
  await expect(page.getByRole('status')).toHaveText('Access denied: 503');
  await expect(page.getByRole('status')).not.toContainText('"value"');
});
