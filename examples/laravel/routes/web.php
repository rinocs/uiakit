<?php

declare(strict_types=1);

use Illuminate\Support\Facades\Route;
use UniversalAIKit\Laravel\WidgetSessionController;

// Register in the host application's web.php, which already applies web/session/CSRF middleware.
Route::post('/uai/widget/session', WidgetSessionController::class)
    ->middleware(['auth', 'throttle:10,1']);
