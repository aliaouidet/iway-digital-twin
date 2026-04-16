import { Component, OnInit, OnDestroy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterModule, Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { AuthService } from '../../core/services/auth.service';
import { ThemeService } from '../../core/services/theme.service';
import { WebSocketService } from '../../core/services/websocket.service';

@Component({
  selector: 'app-admin-layout',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterModule],
  template: `
    <div class="flex h-screen transition-colors duration-300"
      [class]="isDark() ? 'bg-[#020617] text-slate-200' : 'bg-slate-50 text-slate-800'">

      <!-- Sidebar -->
      <aside class="w-64 flex flex-col border-r z-10 flex-shrink-0 transition-colors"
        [class]="isDark() ? 'bg-[#0F172A] border-slate-800' : 'bg-white border-slate-200'">
        <div class="p-6 text-xl font-bold tracking-wider flex items-center gap-3 border-b"
          [class]="isDark() ? 'border-slate-800' : 'border-slate-200'">
          <div class="w-9 h-9 bg-gradient-to-br from-indigo-500 to-indigo-700 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <svg class="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"/></svg>
          </div>
          <span style="font-family: 'Figtree', sans-serif;" [class]="isDark() ? 'text-white' : 'text-slate-900'">I-Way AI</span>
        </div>
        <nav class="flex-1 px-4 py-6 space-y-1 overflow-y-auto">
          <div class="text-[10px] font-semibold uppercase tracking-[0.15em] mb-3 mt-1 px-3"
            [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">Monitoring</div>

          <a routerLink="/admin/dashboard" routerLinkActive="active-link"
            class="nav-link flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all text-sm font-medium cursor-pointer border-l-2 border-transparent"
            [class]="isDark() ? 'text-slate-400 hover:text-slate-200 hover:bg-white/5' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'">
            <svg class="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"/></svg>
            Dashboard
          </a>
          <a routerLink="/admin/tickets" routerLinkActive="active-link"
            class="nav-link flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all text-sm font-medium cursor-pointer border-l-2 border-transparent"
            [class]="isDark() ? 'text-slate-400 hover:text-slate-200 hover:bg-white/5' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'">
            <svg class="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M16.5 6v.75m0 3v.75m0 3v.75m0 3V18m-9-5.25h5.25M7.5 15h3M3.375 5.25c-.621 0-1.125.504-1.125 1.125v3.026a2.999 2.999 0 010 5.198v3.026c0 .621.504 1.125 1.125 1.125h17.25c.621 0 1.125-.504 1.125-1.125v-3.026a2.999 2.999 0 010-5.198V6.375c0-.621-.504-1.125-1.125-1.125H3.375z"/></svg>
            Tickets & Alerts
          </a>

          <div class="text-[10px] font-semibold uppercase tracking-[0.15em] mb-3 mt-6 px-3"
            [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">System</div>

          <a routerLink="/admin/logs" routerLinkActive="active-link"
            class="nav-link flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all text-sm font-medium cursor-pointer border-l-2 border-transparent"
            [class]="isDark() ? 'text-slate-400 hover:text-slate-200 hover:bg-white/5' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'">
            <svg class="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/></svg>
            Logs & Audit
          </a>
          <a routerLink="/admin/insights" routerLinkActive="active-link"
            class="nav-link flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all text-sm font-medium cursor-pointer border-l-2 border-transparent"
            [class]="isDark() ? 'text-slate-400 hover:text-slate-200 hover:bg-white/5' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'">
            <svg class="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5M9 11.25v1.5M12 9v3.75m3-6v6"/></svg>
            AI Insights
          </a>
          <a routerLink="/admin/config" routerLinkActive="active-link"
            class="nav-link flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all text-sm font-medium cursor-pointer border-l-2 border-transparent"
            [class]="isDark() ? 'text-slate-400 hover:text-slate-200 hover:bg-white/5' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'">
            <svg class="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
            System Config
          </a>
        </nav>

        <!-- User Info -->
        <div class="p-4 border-t" [class]="isDark() ? 'border-slate-800' : 'border-slate-200'">
          <div class="flex items-center gap-3 px-2">
            <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
              {{userInitials()}}
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-semibold truncate" [class]="isDark() ? 'text-white' : 'text-slate-900'">{{userName()}}</div>
              <div class="text-xs" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">{{userRole()}}</div>
            </div>
            <div class="flex items-center gap-1">
              <button (click)="toggleTheme()"
                class="p-2 rounded-lg transition-colors cursor-pointer"
                [class]="isDark() ? 'hover:bg-slate-800 text-slate-500' : 'hover:bg-slate-100 text-slate-400'">
                <svg *ngIf="isDark()" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"/></svg>
                <svg *ngIf="!isDark()" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"/></svg>
              </button>
              <button (click)="logout()" class="p-2 rounded-lg transition-colors cursor-pointer"
                [class]="isDark() ? 'hover:bg-slate-800 text-slate-500 hover:text-rose-400' : 'hover:bg-slate-100 text-slate-400 hover:text-rose-500'" title="Logout">
                <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9"/></svg>
              </button>
            </div>
          </div>
        </div>
      </aside>

      <!-- Main Content -->
      <main class="flex-1 flex flex-col overflow-hidden relative">
        <header class="h-14 flex items-center px-8 justify-between sticky top-0 z-20 border-b backdrop-blur-md"
          [class]="isDark() ? 'bg-[#0F172A]/80 border-slate-800' : 'bg-white/80 border-slate-200'">
          <h2 class="text-base font-semibold" style="font-family: 'Figtree', sans-serif;"
            [class]="isDark() ? 'text-slate-200' : 'text-slate-800'">Support Operations Center</h2>
          <div class="flex items-center space-x-5">
            <div class="flex items-center gap-2">
              <span class="relative flex h-2.5 w-2.5"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span><span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span></span>
              <span class="text-xs font-medium" [class]="isDark() ? 'text-slate-400' : 'text-slate-500'">RAG Engine Online</span>
            </div>
          </div>
        </header>
        <div class="flex-1 overflow-auto p-6 lg:p-8">
          <router-outlet></router-outlet>
        </div>
      </main>
    </div>
  `,
  styles: [`
    :host ::ng-deep .active-link {
      border-left-color: #6366f1 !important;
      color: #818cf8 !important;
      background: rgba(99, 102, 241, 0.05);
    }
    :host-context(.dark) ::ng-deep .active-link {
      background: rgba(99, 102, 241, 0.1);
    }
  `]
})
export class AdminLayoutComponent implements OnInit, OnDestroy {
  private authSub?: Subscription;
  userName = signal('');
  userRole = signal('');
  userInitials = signal('');

  constructor(
    private authService: AuthService,
    private themeService: ThemeService,
    private wsService: WebSocketService,
    private router: Router
  ) {}

  isDark = () => this.themeService.isDark();
  toggleTheme = () => this.themeService.toggleTheme();

  ngOnInit(): void {
    this.authSub = this.authService.user$.subscribe(user => {
      if (user) {
        this.userName.set(`${user.prenom} ${user.nom}`);
        this.userRole.set(user.role);
        this.userInitials.set(`${user.prenom[0]}${user.nom[0]}`);
        this.wsService.connect();
      } else {
        this.wsService.disconnect();
      }
    });
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/login']);
  }

  ngOnDestroy(): void {
    this.authSub?.unsubscribe();
    this.wsService.disconnect();
  }
}
