import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ToastService, ToastItem } from '../../core/services/toast.service';

@Component({
  selector: 'app-toast',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="fixed top-5 right-5 z-[9999] flex flex-col gap-2.5 pointer-events-none" style="max-width: 380px;">
      <div *ngFor="let toast of toastService.toasts(); trackBy: trackById"
        class="pointer-events-auto rounded-xl border shadow-2xl backdrop-blur-lg overflow-hidden transform transition-all duration-300 animate-slideIn"
        [class]="getToastClass(toast)">
        <div class="flex items-start gap-3 px-4 py-3">
          <!-- Icon -->
          <div class="flex-shrink-0 mt-0.5" [innerHTML]="getIcon(toast.type)"></div>
          <!-- Message -->
          <p class="flex-1 text-sm font-medium leading-snug" [class]="getTextClass(toast)">{{toast.message}}</p>
          <!-- Dismiss -->
          <button (click)="toastService.dismiss(toast.id)"
            class="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-md opacity-50 hover:opacity-100 transition-opacity cursor-pointer"
            [class]="getDismissClass(toast)">
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <!-- Progress bar -->
        <div class="h-0.5 w-full opacity-30" [class]="getProgressBg(toast)">
          <div class="h-full animate-shrink" [class]="getProgressFill(toast)"
            [style.animation-duration.ms]="toast.duration"></div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    @keyframes slideIn {
      from { opacity: 0; transform: translateX(100%) scale(0.95); }
      to   { opacity: 1; transform: translateX(0) scale(1); }
    }
    .animate-slideIn { animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards; }

    @keyframes shrink {
      from { width: 100%; }
      to   { width: 0%; }
    }
    .animate-shrink { animation: shrink linear forwards; }
  `]
})
export class ToastComponent {
  constructor(public toastService: ToastService) {}

  trackById(_: number, item: ToastItem): number { return item.id; }

  getToastClass(t: ToastItem): string {
    switch (t.type) {
      case 'success': return 'bg-emerald-950/90 border-emerald-500/30';
      case 'warning': return 'bg-amber-950/90 border-amber-500/30';
      case 'error':   return 'bg-rose-950/90 border-rose-500/30';
      default:        return 'bg-slate-900/90 border-indigo-500/30';
    }
  }

  getTextClass(t: ToastItem): string {
    switch (t.type) {
      case 'success': return 'text-emerald-200';
      case 'warning': return 'text-amber-200';
      case 'error':   return 'text-rose-200';
      default:        return 'text-indigo-200';
    }
  }

  getDismissClass(t: ToastItem): string {
    switch (t.type) {
      case 'success': return 'text-emerald-400';
      case 'warning': return 'text-amber-400';
      case 'error':   return 'text-rose-400';
      default:        return 'text-indigo-400';
    }
  }

  getProgressBg(t: ToastItem): string {
    switch (t.type) {
      case 'success': return 'bg-emerald-900';
      case 'warning': return 'bg-amber-900';
      case 'error':   return 'bg-rose-900';
      default:        return 'bg-indigo-900';
    }
  }

  getProgressFill(t: ToastItem): string {
    switch (t.type) {
      case 'success': return 'bg-emerald-400';
      case 'warning': return 'bg-amber-400';
      case 'error':   return 'bg-rose-400';
      default:        return 'bg-indigo-400';
    }
  }

  getIcon(type: string): string {
    switch (type) {
      case 'success': return '<svg class="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>';
      case 'warning': return '<svg class="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>';
      case 'error': return '<svg class="w-5 h-5 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/></svg>';
      default: return '<svg class="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z"/></svg>';
    }
  }
}
