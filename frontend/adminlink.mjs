import { chromium } from 'playwright';
const b = await chromium.launch({ args: ['--no-sandbox'] });
const ctx = await b.newContext({ viewport: { width: 500, height: 900 } });
const page = await ctx.newPage();
page.on('dialog', async (d) => { console.log('dialog:', d.message()); await d.accept(); });
page.on('pageerror', (e) => console.log('pageerror:', e.message));

// Super admin login screen should no longer show a role toggle
await page.goto('http://localhost:5180/admin/login', { waitUntil: 'networkidle' });
await page.waitForTimeout(500);
await page.screenshot({ path: '/tmp/pw-test/al1-login.png' });

await page.fill('input[type=password]', '0000');
await page.click('button[type=submit]');
await page.waitForSelector('text=賽事設定');
await page.click('text=隊伍');
await page.waitForTimeout(500);
await page.screenshot({ path: '/tmp/pw-test/al2-teamstab.png' });

// grab the admin link text
const adminLinkEl = await page.locator('a.text-amber-300').first();
const adminUrl = await adminLinkEl.getAttribute('href');
console.log('admin link:', adminUrl);

await b.close();
