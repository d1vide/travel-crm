const form = document.getElementById('checkout');
const error = document.getElementById('checkout-error');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const outcome = event.submitter?.value;
  if (!['succeeded', 'failed', 'timeout'].includes(outcome)) return;
  const buttons = form.querySelectorAll('button');
  buttons.forEach((button) => { button.disabled = true; });
  error.hidden = true;
  try {
    // CORS mode retains Origin while no-referrer protects the checkout URL.
    const response = await fetch(window.location.pathname, {
      method: 'POST',
      mode: 'cors',
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ outcome }).toString(),
    });
    if (!response.ok) {
      error.textContent = 'Не удалось сохранить результат. Обновите страницу и повторите.';
      error.hidden = false;
      return;
    }
    window.location.reload();
  } catch {
    error.textContent = 'Нет связи с сервисом. Обновите страницу и повторите.';
    error.hidden = false;
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
  }
});
