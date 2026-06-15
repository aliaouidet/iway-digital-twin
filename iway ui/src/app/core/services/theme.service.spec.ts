import { TestBed } from '@angular/core/testing';
import { ThemeService } from './theme.service';

describe('ThemeService', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove('dark');
    TestBed.configureTestingModule({ providers: [ThemeService] });
  });

  it('defaults to dark and applies the dark class', () => {
    const svc = TestBed.inject(ThemeService);
    expect(svc.isDark()).toBe(true);
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('honours a stored light preference', () => {
    localStorage.setItem('iway_theme', 'light');
    const svc = TestBed.inject(ThemeService);
    expect(svc.isDark()).toBe(false);
  });

  it('toggleTheme flips the signal', () => {
    const svc = TestBed.inject(ThemeService);
    expect(svc.isDark()).toBe(true);
    svc.toggleTheme();
    expect(svc.isDark()).toBe(false);
    svc.toggleTheme();
    expect(svc.isDark()).toBe(true);
  });
});
