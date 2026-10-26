import { connectChat } from '/assets/widget/index.js';

const status = document.querySelector('#status');
try {
  await connectChat(document.querySelector('#chat'), { sessionUrl: '/widget/session' });
  status.textContent = 'Connected';
} catch {
  status.textContent = 'Unable to start a session. Sign in and reload to try again.';
}
