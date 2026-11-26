import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const script = readFileSync(new URL('./checkout.js', import.meta.url), 'utf8');

function page(fetch) {
  const buttons = [{ disabled: false }, { disabled: false }, { disabled: false }];
  const error = { hidden: true, textContent: '' };
  let submit;
  let reloads = 0;
  const form = {
    addEventListener(name, listener) { assert.equal(name, 'submit'); submit = listener; },
    querySelectorAll() { return buttons; },
  };
  vm.runInNewContext(script, {
    document: { getElementById: (id) => id === 'checkout' ? form : error },
    window: { location: { pathname: '/payment-stub/pay/test-only-token', reload() { reloads++; } } },
    URLSearchParams,
    fetch,
  });
  return { buttons, error, reloads: () => reloads, submit: (value) => submit({ preventDefault() {}, submitter: { value } }) };
}

test('submission protects the URL, omits staff credentials and waits before reload', async () => {
  let finish;
  const view = page(async (url, options) => {
    assert.equal(url, '/payment-stub/pay/test-only-token');
    assert.equal(options.mode, 'cors');
    assert.equal(options.credentials, 'omit');
    assert.equal(options.referrerPolicy, 'no-referrer');
    assert.equal(options.body, 'outcome=succeeded');
    return new Promise((resolve) => { finish = resolve; });
  });
  const saving = view.submit('succeeded');
  assert.ok(view.buttons.every((button) => button.disabled));
  assert.equal(view.reloads(), 0);
  finish({ ok: true });
  await saving;
  assert.equal(view.reloads(), 1);
});

test('HTTP refusal keeps the page and permits retry without showing a false success', async () => {
  const view = page(async () => ({ ok: false }));
  await view.submit('failed');
  assert.equal(view.reloads(), 0);
  assert.equal(view.error.hidden, false);
  assert.ok(view.buttons.every((button) => !button.disabled));
});

test('network errors do not disclose internal exception text', async () => {
  const view = page(async () => { throw new Error('PRIVATE-CHECKOUT-URL'); });
  await view.submit('timeout');
  assert.equal(view.error.hidden, false);
  assert.ok(!view.error.textContent.includes('PRIVATE-CHECKOUT-URL'));
  assert.equal(view.reloads(), 0);
});

test('an unknown action cannot issue a request', async () => {
  let requests = 0;
  const view = page(async () => { requests++; });
  await view.submit('unknown');
  assert.equal(requests, 0);
});
