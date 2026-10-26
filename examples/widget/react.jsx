import { useEffect, useRef } from 'react';
import '@universal-ai-kit/chat-widget';

export function SupportChat() {
  const ref = useRef(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    let cancelled = false;

    fetch('/api/widget-token', { method: 'POST' })
      .then((response) => {
        if (!response.ok) throw new Error('widget token unavailable');
        return response.json();
      })
      .then(({ token, conversation_id }) => {
        if (cancelled) return;
        element.setConfig({
          baseUrl: window.location.origin,
          token,
          conversationId: conversation_id,
        });
      })
      .catch((error) => {
        element.setConfig({ onError: () => console.error(error) });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return <uai-chat ref={ref} title="Supporto" theme="light" />;
}
