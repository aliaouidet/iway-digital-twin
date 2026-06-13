import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

/**
 * Reusable error state for data-fetching pages. Replaces the silent failures
 * where a failed HTTP call left a blank page. Admin zone is English; pass
 * `message`/`hint`/`retryLabel` to localize for the French zones.
 */
@Component({
  selector: 'app-error-banner',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div role="alert" class="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 rounded-2xl p-5 flex items-center gap-4">
      <div class="w-9 h-9 rounded-xl bg-rose-100 dark:bg-rose-900/40 flex items-center justify-center flex-shrink-0">
        <svg class="w-5 h-5 text-rose-600 dark:text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/>
        </svg>
      </div>
      <div class="flex-1 min-w-0">
        <p class="text-sm font-semibold text-rose-700 dark:text-rose-300">{{ message || 'Something went wrong.' }}</p>
        <p class="text-xs text-rose-600/70 dark:text-rose-400/70 mt-0.5">{{ hint || 'Check your connection and try again.' }}</p>
      </div>
      <button (click)="retry.emit()" type="button"
        class="px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer flex-shrink-0 bg-rose-600 hover:bg-rose-500 text-white transition-colors">
        {{ retryLabel || 'Retry' }}
      </button>
    </div>
  `
})
export class ErrorBannerComponent {
  @Input() message = '';
  @Input() hint = '';
  @Input() retryLabel = '';
  @Output() retry = new EventEmitter<void>();
}
