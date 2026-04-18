import { Injectable, signal } from '@angular/core';

export type ToastType = 'success' | 'info' | 'warning' | 'error';

export interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
  duration: number;
  createdAt: number;
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  private _counter = 0;
  toasts = signal<ToastItem[]>([]);

  show(message: string, type: ToastType = 'info', duration: number = 4000): void {
    const id = ++this._counter;
    const toast: ToastItem = { id, message, type, duration, createdAt: Date.now() };

    this.toasts.update(list => {
      const next = [...list, toast];
      // Keep max 5 toasts visible
      return next.length > 5 ? next.slice(-5) : next;
    });

    // Auto-dismiss
    setTimeout(() => this.dismiss(id), duration);
  }

  dismiss(id: number): void {
    this.toasts.update(list => list.filter(t => t.id !== id));
  }
}
