import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { ThemeService } from '../../../core/services/theme.service';
import { IwayLogoComponent } from '../../../shared/components/iway-logo.component';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, IwayLogoComponent],
  template: `
    <div class="min-h-screen flex items-center justify-center p-4 transition-colors duration-300"
         [class]="isDark() ? 'bg-[#020617]' : 'bg-gradient-to-br from-slate-50 to-indigo-50'">

      <!-- Theme Toggle -->
      <button (click)="toggleTheme()" class="absolute top-6 right-6 w-10 h-10 rounded-xl flex items-center justify-center transition-colors cursor-pointer"
        [class]="isDark() ? 'bg-slate-800 hover:bg-slate-700 text-slate-400' : 'bg-white shadow hover:bg-slate-50 text-slate-600'">
        <svg *ngIf="isDark()" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"/></svg>
        <svg *ngIf="!isDark()" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"/></svg>
      </button>

      <div class="w-full max-w-md space-y-8">
        <!-- Logo -->
        <div class="flex justify-center">
          <div class="w-96 mb-8 translate-x-4">
            <app-iway-logo [dark]="isDark()" [compact]="false" width="100%"></app-iway-logo>
          </div>
        </div>

        <!-- Login Card -->
        <div class="rounded-2xl border p-8 space-y-6 transition-colors"
          [class]="isDark() ? 'bg-[#0F172A] border-slate-800' : 'bg-white border-slate-200 shadow-xl shadow-slate-200/50'">
          <h2 class="text-lg font-bold" [class]="isDark() ? 'text-white' : 'text-slate-900'" style="font-family: 'Figtree', sans-serif;">Sign in to your account</h2>

          <div *ngIf="error()" class="px-4 py-3 rounded-xl text-sm"
            [class]="isDark() ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' : 'bg-rose-50 text-rose-600 border border-rose-200'">
            {{error()}}
          </div>

          <form (ngSubmit)="onLogin()" class="space-y-4">
            <div>
              <label class="text-[10px] font-semibold uppercase tracking-wider block mb-1.5"
                [class]="isDark() ? 'text-slate-500' : 'text-slate-500'">Matricule</label>
              <input [(ngModel)]="matricule" name="matricule" placeholder="Enter your matricule"
                class="w-full px-4 py-3 rounded-xl text-sm transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                [class]="isDark() ? 'bg-slate-800/50 border border-slate-700 text-white placeholder-slate-500' : 'bg-slate-50 border border-slate-200 text-slate-900 placeholder-slate-400'" />
            </div>
            <div>
              <label class="text-[10px] font-semibold uppercase tracking-wider block mb-1.5"
                [class]="isDark() ? 'text-slate-500' : 'text-slate-500'">Password</label>
              <input [(ngModel)]="password" name="password" type="password" placeholder="Enter your password"
                class="w-full px-4 py-3 rounded-xl text-sm transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                [class]="isDark() ? 'bg-slate-800/50 border border-slate-700 text-white placeholder-slate-500' : 'bg-slate-50 border border-slate-200 text-slate-900 placeholder-slate-400'" />
            </div>
            <button type="submit" [disabled]="isLoading()"
              class="w-full py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl transition-colors cursor-pointer disabled:opacity-50 text-sm">
              {{isLoading() ? 'Signing in...' : 'Sign In'}}
            </button>
          </form>

          <div class="flex items-center gap-3">
            <div class="flex-1 h-px" [class]="isDark() ? 'bg-slate-800' : 'bg-slate-200'"></div>
            <span class="text-[10px] font-semibold uppercase tracking-wider" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">Quick Access</span>
            <div class="flex-1 h-px" [class]="isDark() ? 'bg-slate-800' : 'bg-slate-200'"></div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <button *ngFor="let p of personas" (click)="quickLogin(p.matricule, p.password)"
              class="p-3 rounded-xl border text-left transition-all cursor-pointer group"
              [class]="isDark()
                ? 'bg-slate-800/30 border-slate-700/50 hover:border-slate-600'
                : 'bg-slate-50 border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/50'">
              <div class="flex items-center gap-2.5 mb-1">
                <div class="w-7 h-7 rounded-lg flex items-center justify-center text-[10px] font-bold text-white flex-shrink-0"
                  [style.background]="p.color">{{p.initials}}</div>
                <div class="min-w-0">
                  <div class="text-xs font-semibold truncate" [class]="isDark() ? 'text-white' : 'text-slate-900'">{{p.name}}</div>
                  <div class="text-[10px]" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">{{p.role}}</div>
                </div>
              </div>
            </button>
          </div>
        </div>
      </div>
    </div>
  `
})
export class LoginComponent {
  matricule = '';
  password = '';
  isLoading = signal(false);
  error = signal('');

  personas = [
    { name: 'Nadia Mansour', role: 'Adherent', matricule: '12345', password: 'pass', initials: 'NM', color: '#6366f1' },
    { name: 'Dr. Amine Zaid', role: 'Prestataire', matricule: '99999', password: 'med', initials: 'AZ', color: '#10b981' },
    { name: 'Karim Belhadj', role: 'Agent', matricule: '88888', password: 'agent', initials: 'KB', color: '#f59e0b' },
    { name: 'Sara Toumi', role: 'Admin', matricule: '77777', password: 'admin', initials: 'ST', color: '#06b6d4' },
  ];

  constructor(
    private authService: AuthService,
    private themeService: ThemeService,
    private router: Router
  ) {}

  isDark = () => this.themeService.isDark();
  toggleTheme = () => this.themeService.toggleTheme();

  quickLogin(matricule: string, password: string): void {
    this.matricule = matricule;
    this.password = password;
    this.onLogin();
  }

  onLogin(): void {
    if (!this.matricule || !this.password) return;
    this.isLoading.set(true);
    this.error.set('');

    this.authService.login({ matricule: this.matricule, password: this.password }).subscribe({
      next: () => {
        this.isLoading.set(false);
        this.router.navigate([this.authService.getHomeRoute()]);
      },
      error: (err) => {
        this.isLoading.set(false);
        this.error.set(err?.error?.detail || 'Authentication failed');
      }
    });
  }
}
