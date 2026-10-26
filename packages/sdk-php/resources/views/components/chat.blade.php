@props(['title' => 'Chat', 'theme' => 'light', 'placeholder' => 'Type a message…', 'sessionUrl' => '/uai/widget/session'])
<div data-uai-widget>
    <uai-chat title="{{ $title }}" theme="{{ $theme }}" placeholder="{{ $placeholder }}" data-session-url="{{ $sessionUrl }}"></uai-chat>
    <p role="status" aria-live="polite"></p>
</div>
