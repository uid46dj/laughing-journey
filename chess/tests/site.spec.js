import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFile } from 'node:fs/promises';

const widths = [320, 375, 390, 430, 768, 1024, 1280, 1440, 1920, 2560];
const sections = ['pen', 'atelier', 'craft', 'details', 'personalise', 'reserve'];

for (const width of widths) {
  test(`responsive composition and all section destinations at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/');
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Make yourmark.');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    for (const id of sections) {
      await page.goto(`/#${id}`);
      const section = page.locator(`#${id}`);
      await expect(section).toBeInViewport();
      await expect(section.getByRole('heading').first()).toBeVisible();
      const overflow = await section.locator('h1, h2, .button, .feature-tab, input').evaluateAll((elements) => elements.filter((element) => {
        const box = element.getBoundingClientRect();
        return box.width > 0 && (box.left < -1 || box.right > innerWidth + 1);
      }).map((element) => element.textContent));
      expect(overflow).toEqual([]);
    }
    await page.goto('/');
    await page.screenshot({ path: testInfo.outputPath(`vale-${width}.png`), fullPage: true });
    expect(errors).toEqual([]);
  });
}

test('every in-page link has a real destination; metadata and local assets load', async ({ page, request }) => {
  const failed = [];
  page.on('requestfailed', (request) => failed.push(request.url()));
  await page.goto('/');
  expect(await page.locator('a[href^="#"]').evaluateAll((links) => links.filter((link) => !document.getElementById(link.hash.slice(1))).map((link) => link.hash))).toEqual([]);
  await expect(page).toHaveTitle('VALÉ — Obsidian No. 01 · Make your mark.');
  await expect(page.locator('meta[name="description"]')).toHaveAttribute('content', /£285/);
  await expect(page.locator('h1')).toHaveCount(1);
  await expect(page.locator('meta[property="og:image:alt"]')).toHaveAttribute('content', /Obsidian/);
  expect((await request.get('/vale-obsidian-social.png')).ok()).toBe(true);
  expect((await request.get('/favicon.svg')).ok()).toBe(true);
  expect(await (await request.get('/robots.txt')).text()).toContain('User-agent: *');
  expect(await page.evaluate(() => performance.getEntriesByType('resource').filter((entry) => !entry.name.startsWith(location.origin)).map((entry) => entry.name))).toEqual([]);
  expect(failed).toEqual([]);
});

test('engineering is operable by pointer and the complete tab keyboard pattern', async ({ page }) => {
  await page.goto('/#craft');
  const tabs = page.getByRole('tab');
  await tabs.nth(1).click();
  await expect(tabs.nth(1)).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tabpanel')).toContainText('components');
  await page.keyboard.press('ArrowDown');
  await expect(tabs.nth(2)).toBeFocused();
  await expect(page.getByRole('tabpanel')).toContainText('800');
  await page.keyboard.press('ArrowDown');
  await expect(tabs.nth(0)).toBeFocused();
  await page.keyboard.press('End');
  await expect(tabs.nth(2)).toBeFocused();
  await page.keyboard.press('Home');
  await expect(tabs.nth(0)).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.locator('.engineering-controls > a')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('tabpanel')).toBeFocused();
});

test('live engraving, view controls, character limit and confirmation carry through to reservation', async ({ page }) => {
  await page.goto('/#personalise');
  const input = page.getByLabel('Engrave your mark');
  await expect(page.getByRole('button', { name: 'Choose this engraving' })).toBeDisabled();
  await input.fill('alexander');
  await expect(input).toHaveValue('ALEXANDER');
  await expect(page.locator('.engraving-art text')).toHaveText('ALEXANDER');
  await page.getByRole('button', { name: 'Full pen', exact: true }).click();
  await expect(page.locator('.engraving-art svg')).toHaveAttribute('viewBox', '0 0 1000 240');
  await page.getByRole('button', { name: 'Detail', exact: true }).click();
  await expect(page.locator('.engraving-art svg')).toHaveAttribute('viewBox', '340 83 330 80');
  await input.fill('ABCDEFGHIJKLMNOPQRST');
  await expect(input).toHaveValue('ABCDEFGHIJKLMNOP');
  await page.getByRole('button', { name: 'Clear engraving' }).click();
  await expect(input).toBeFocused();
  await expect(input).toHaveValue('');
  await page.getByRole('button', { name: 'YOURS, ALWAYS', exact: true }).click();
  await page.getByRole('button', { name: 'Choose this engraving' }).click();
  await expect(page.locator('#reserve-title')).toBeFocused();
  await expect(page.locator('.selected-engraving')).toHaveText('YOURS, ALWAYS');
  await page.getByRole('button', { name: 'Reserve your Obsidian' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('YOURS, ALWAYS');
  await dialog.getByRole('button', { name: 'Edit engraving' }).click();
  await expect(dialog).not.toBeVisible();
  await expect(input).toBeFocused();
});

test('selection review is honest, saves locally, restores on reload and downloads a summary', async ({ page }) => {
  await page.goto('/#personalise');
  await page.getByLabel('Engrave your mark').fill('E. W.');
  await page.getByRole('button', { name: 'Reserve your Obsidian' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('No payment or reservation is processed here.');
  await dialog.getByRole('button', { name: 'Save your selection' }).click();
  await expect(dialog.getByRole('status')).toContainText('Selection saved on this device. No reservation has been placed.');
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('vale-selection')))).toEqual({ product: 'Obsidian No. 01', engraving: 'E. W.', priceGBP: 285 });
  const downloadPromise = page.waitForEvent('download');
  await dialog.getByRole('button', { name: 'Download selection (.txt)' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('vale-obsidian-no-01-selection.txt');
  const text = await readFile(await download.path(), 'utf8');
  expect(text).toContain('Engraving: E. W.');
  expect(text).toContain('This summary is not an order or reservation confirmation.');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Reserve your Obsidian' })).toBeFocused();
  await page.reload();
  await expect(page.getByLabel('Engrave your mark')).toHaveValue('E. W.');
});

test('unavailable storage produces an honest fallback; invalid saved data is ignored', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('vale-selection', '{invalid-json');
    Storage.prototype.setItem = () => { throw new Error('Storage is unavailable'); };
  });
  await page.goto('/#reserve');
  await expect(page.getByLabel('Engrave your mark')).toHaveValue('');
  await page.getByRole('button', { name: 'Reserve your Obsidian' }).click();
  await page.getByRole('button', { name: 'Save your selection' }).click();
  await expect(page.getByRole('dialog').getByRole('status')).toContainText('could not be saved');
  await expect(page.getByRole('button', { name: 'Download selection (.txt)' })).toBeEnabled();
});

test('modal traps keyboard focus, preserves scroll, and closes on backdrop', async ({ page }) => {
  await page.goto('/#reserve');
  await page.getByRole('button', { name: 'Reserve your Obsidian' }).click();
  const y = await page.evaluate(() => scrollY);
  await expect(page.getByRole('button', { name: 'Close dialog' })).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByRole('button', { name: 'Download selection (.txt)' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Close dialog' })).toBeFocused();
  await page.mouse.wheel(0, 600);
  expect(await page.evaluate(() => scrollY)).toBe(y);
  await page.mouse.click(12, 200);
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Reserve your Obsidian' })).toBeFocused();
  expect(await page.evaluate(() => document.body.style.overflowY)).toBe('');
});

test('mobile navigation is keyboard accessible, closes after a destination, and restores scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  const opener = page.getByRole('button', { name: 'Open menu' });
  await opener.click();
  await expect(opener).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('button', { name: 'Close dialog' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(opener).toBeFocused();
  await opener.click();
  await page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name: 'Personalise' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.locator('#personalise')).toBeFocused();
  await expect(page.locator('#personalise')).toBeInViewport();
  expect(await page.evaluate(() => document.body.style.overflowY)).toBe('');
  await opener.click();
  await page.setViewportSize({ width: 1024, height: 900 });
  await expect(page.getByRole('dialog')).not.toBeVisible();
});

test('care and contact are real information dialogs, not placeholder links', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Care guide' }).click();
  await expect(page.getByRole('dialog')).toContainText('Care for the finish');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Contact', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('no messages or personal details are collected here');
  await page.getByRole('button', { name: 'Explore your selection' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(1);
  await expect(page.getByRole('dialog')).toContainText('A considered choice.');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Reserve your Obsidian' })).toBeFocused();
  expect(await page.evaluate(() => document.body.style.overflowY)).toBe('');
});

for (const width of [390, 1440]) {
  test(`WCAG A/AA automated checks for page and open interfaces at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/');
    const audit = async () => {
      const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      expect(result.violations).toEqual([]);
    };
    await audit();
    for (const name of ['Reserve your Obsidian', 'Care guide', 'Contact']) {
      await page.getByRole('button', { name, exact: true }).click();
      await audit();
      await page.keyboard.press('Escape');
    }
    if (width < 760) {
      await page.getByRole('button', { name: 'Open menu' }).click();
      await audit();
    }
  });
}

test('reduced motion disables animations while every section remains visible', async ({ page }) => {
  await page.goto('/');
  expect(await page.locator('.reveal-pending').count()).toBe(0);
  expect(await page.evaluate(() => document.getAnimations().length)).toBe(0);
  for (const id of sections) await expect(page.locator(`#${id}`)).toHaveCSS('opacity', '1');
});

test('normal motion reveals complete content and never loops indefinitely', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/');
  for (const element of await page.locator('[data-reveal]').all()) {
    await element.scrollIntoViewIfNeeded();
    await expect(element).not.toHaveClass(/reveal-pending/);
    await expect(element).toHaveCSS('opacity', '1');
  }
  expect(await page.evaluate(() => document.getAnimations().filter((animation) => animation.effect.getTiming().iterations === Infinity).length)).toBe(0);
});
