// Trusted adapter. Input is image bytes, never a submitted script or URL.
const fs = require('node:fs');

(async () => {
  let browser;
  let deadline;
  let responded = false;
  const respond = value => {
    if (!responded) {
      responded = true;
      process.stdout.write(JSON.stringify(value));
    }
  };
  try {
    const {chromium} = require('playwright');
    const input = JSON.parse(fs.readFileSync(0, 'utf8'));
    const deadlineMs = Math.max(1, input.deadlineMs || 14000);
    deadline = setTimeout(async () => {
      respond({status: 'unavailable', message: 'Image decoder operational deadline exceeded.'});
      if (browser) await browser.close();
    }, deadlineMs);
    browser = await chromium.launch({headless: true, timeout: deadlineMs});
    const context = await browser.newContext({serviceWorkers: 'block'});
    await context.route('**/*', route => route.abort());
    const page = await context.newPage();
    const result = await page.evaluate(async ({bytes, mediaType}) => {
      try {
        const img = new Image();
        img.src = `data:${mediaType};base64,${bytes}`;
        await img.decode();
        return img.naturalWidth > 0 && img.naturalHeight > 0
          ? {status: 'ok', message: 'Image decoded; authenticity is not checked.'}
          : {status: 'invalid', message: 'Image has no decoded dimensions.'};
      } catch {
        return {status: 'invalid', message: 'Image bytes could not be decoded.'};
      }
    }, input);
    respond(result);
  } catch {
    respond({status: 'unavailable', message: 'Image decoder runtime unavailable.'});
  } finally {
    clearTimeout(deadline);
    if (browser) await browser.close();
  }
})();
