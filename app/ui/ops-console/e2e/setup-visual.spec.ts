import { expect, test } from '@playwright/test';

test.describe('Setup visual regression', () => {
  const viewports = [
    { width: 1366, height: 768 },
    { width: 1920, height: 1080 },
  ];

  for (const viewport of viewports) {
    test(`setup workflow spacing ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto('/?tab=setup');

      const setupWorkflow = page.locator('.setup-workflow-page');
      await expect(setupWorkflow).toBeVisible();

      const box = await setupWorkflow.boundingBox();
      if (!box) {
        throw new Error('setup-workflow-page bounding box unavailable');
      }
      const screenshot = await page.screenshot({
        animations: 'disabled',
        caret: 'hide',
        scale: 'css',
        clip: {
          x: Math.round(box.x),
          y: Math.round(box.y),
          width: Math.round(box.width),
          height: Math.min(520, Math.round(box.height)),
        },
      });
      expect(screenshot).toMatchSnapshot(`setup-workflow-${viewport.width}x${viewport.height}.png`, {
        maxDiffPixelRatio: 0.01,
      });
    });
  }
});
