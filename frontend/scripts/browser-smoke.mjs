import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

// HTTP fixtures exercise rendering only. They are never shipped as the app's model.
const browser = await chromium.launch({
  channel: process.env.BROWSER_CHANNEL || 'msedge',
  headless: true,
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
const baseUrl = process.env.APP_URL || 'http://127.0.0.1:5173';
const artifactDirectory = '../artifacts/browser';
await mkdir(artifactDirectory, { recursive: true });

try {
  await page.goto(baseUrl);
  await expect(page.getByRole('heading', { name: 'Ask. Explore. Understand.' })).toBeVisible();
  await expect(page.locator('.schema-table')).toHaveCount(4);
  await page.screenshot({ path: `${artifactDirectory}/desktop.png`, fullPage: true });
  await page.getByRole('button', { name: /Explore customers/ }).click();
  await expect(page.getByLabel('Ask about your data')).toHaveValue(
    'Show all customers and their states',
  );

  const successfulResponse = {
    status: 'success',
    intent: 'query',
    generated_sql: 'SELECT name, state FROM Users;',
    previous_sql: 'SELECT name, state FROM Users;',
    is_valid: true,
    error_msg: null,
    retry_count: 0,
    explanation: 'Lists customers and their states.',
    original_error: null,
    optimization_tips: [],
    query_results: {
      columns: ['name', 'state'],
      rows: [['Maya Chen', 'California']],
      truncated: false,
      elapsed_ms: 1.2,
      row_limit: 200,
    },
  };
  let nextResponse = successfulResponse;
  await page.route('**/api/chat', (route) => route.fulfill({ json: nextResponse }));
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByRole('cell', { name: 'Maya Chen' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Copy SQL' })).toBeEnabled();
  await page.screenshot({ path: `${artifactDirectory}/results.png`, fullPage: true });

  nextResponse = {
    ...successfulResponse,
    status: 'rejected',
    intent: 'out_of_scope',
    generated_sql: null,
    is_valid: false,
    query_results: null,
    explanation: 'I can help with SQL and this ecommerce database.',
  };
  await page.getByLabel('Ask about your data').fill('Who won the World Cup?');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByRole('button', { name: 'Copy SQL' })).toBeDisabled();
  await expect(
    page.getByText('I can help with SQL and this ecommerce database.').first(),
  ).toBeVisible();

  await page.getByRole('button', { name: /New conversation/ }).click();
  await expect(page.getByRole('heading', { name: /Your data has a story/ })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${artifactDirectory}/mobile.png`, fullPage: true, animations: 'disabled' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await expect(page.getByRole('navigation', { name: 'Database schema' })).toBeVisible();
  expect(errors).toEqual([]);
  console.log(
    'Desktop/mobile rendering, query results, refusal, reset, and overflow checks passed.',
  );
} finally {
  await browser.close();
}
