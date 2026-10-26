import { connectChat } from '@universal-ai-kit/chat-widget';

for (const wrapper of document.querySelectorAll('[data-uai-widget]')) {
  const chat = wrapper.querySelector('uai-chat');
  const csrf = document.querySelector('meta[name="csrf-token"]');
  const status = wrapper.querySelector('[role="status"]');
  if (!chat || !csrf) {
    if (status) status.textContent = 'Unable to start chat. Please reload and try again.';
    continue;
  }
  connectChat(chat, {
    sessionUrl: chat.dataset.sessionUrl,
    headers: { 'X-CSRF-TOKEN': csrf.content },
  }).catch(() => {
    if (status) status.textContent = 'Unable to start chat. Please reload and try again.';
  });
}
