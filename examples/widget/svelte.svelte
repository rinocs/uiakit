<script>
  import { onMount } from 'svelte';
  import '@universal-ai-kit/chat-widget';

  let chat;

  onMount(async () => {
    const response = await fetch('/api/widget-token', { method: 'POST' });
    if (!response.ok) throw new Error('widget token unavailable');
    const { token, conversation_id } = await response.json();
    chat.setConfig({
      baseUrl: window.location.origin,
      token,
      conversationId: conversation_id,
    });
  });
</script>

<uai-chat bind:this={chat} title="Supporto" theme="light" />
