import { chromium } from "playwright";
const OUT = process.argv[2];
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1280, height: 900 } });
const p = await ctx.newPage();
await p.goto("http://localhost:3000/login");
await p.fill("#email", "owner@gvcexecutive.in");
await p.fill("#password", "owner@123");
await Promise.all([p.waitForURL("**/sites"), p.click("button[type=submit]")]);
await p.waitForTimeout(800);
let target = null;
for (const l of await p.$$('a[href^="/sites/"]')) {
  if ((await l.innerText()).includes("Kothrud")) target = await l.getAttribute("href");
}
await p.goto("http://localhost:3000" + target + "/expenses");
await p.waitForTimeout(1500);
await p.screenshot({ path: `${OUT}/e-page.png`, fullPage: true });
// Open the form via a "due this month" chip so it arrives pre-filled.
await p.click("button:has-text('Cooking gas')");
await p.waitForTimeout(700);
await p.screenshot({ path: `${OUT}/e-form.png`, fullPage: true });
const m = await ctx.newPage();
await m.setViewportSize({ width: 390, height: 844 });
await m.goto("http://localhost:3000" + target + "/expenses");
await m.waitForTimeout(1500);
await m.screenshot({ path: `${OUT}/e-mobile.png`, fullPage: true });
await b.close();
console.log("done");
