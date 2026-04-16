import { Injectable, signal, effect } from '@angular/core';

export type Theme = 'dark' | 'light';

const THEME_KEY = 'iway_theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  theme = signal<Theme>(this.getStoredTheme());
  isDark = () => this.theme() === 'dark';

  constructor() {
    effect(() => {
      const t = this.theme();
      localStorage.setItem(THEME_KEY, t);
      const html = document.documentElement;
      if (t === 'dark') {
        html.classList.add('dark');
      } else {
        html.classList.remove('dark');
      }
    });
    // Initialize on startup
    this.applyTheme(this.theme());
  }

  toggleTheme(): void {
    this.theme.set(this.isDark() ? 'light' : 'dark');
  }

  private applyTheme(t: Theme): void {
    if (t === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }

  private getStoredTheme(): Theme {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
    return 'dark'; // Default to dark
  }
}
