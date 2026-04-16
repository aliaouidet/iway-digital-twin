import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterModule } from '@angular/router';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterModule],
  template: `
    <div class="flex h-screen bg-gray-50 font-sans text-gray-800">
      <!-- Sidebar -->
      <aside class="w-64 bg-slate-900 text-white flex flex-col shadow-xl z-10">
        <div class="p-6 text-2xl font-bold tracking-wider flex items-center gap-3 border-b border-white/10">
          <div class="w-8 h-8 bg-primary-500 rounded-lg flex items-center justify-center text-sm">🤖</div>
          I-Way AI
        </div>
        <nav class="flex-1 px-4 py-6 space-y-2 overflow-y-auto">
          <div class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-4 mt-2 px-2">Monitoring</div>
          <a routerLink="/dashboard" routerLinkActive="bg-white/10 text-primary-400" class="block px-4 py-3 rounded-xl hover:bg-white/5 transition-all font-medium">Dashboard</a>
          <a routerLink="/tickets" routerLinkActive="bg-white/10 text-primary-400" class="block px-4 py-3 rounded-xl hover:bg-white/5 transition-all font-medium">Tickets & Alerts</a>
          
          <div class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-4 mt-8 px-2">Resolution</div>
          <a routerLink="/chat" routerLinkActive="bg-white/10 text-primary-400" class="block px-4 py-3 rounded-xl hover:bg-white/5 transition-all font-medium">Chat Interface</a>
          
          <div class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-4 mt-8 px-2">System</div>
          <a routerLink="/logs" routerLinkActive="bg-white/10 text-primary-400" class="block px-4 py-3 rounded-xl hover:bg-white/5 transition-all font-medium">Logs & Audit</a>
          <a routerLink="/insights" routerLinkActive="bg-white/10 text-primary-400" class="block px-4 py-3 rounded-xl hover:bg-white/5 transition-all font-medium">AI Insights</a>
          <a routerLink="/admin" routerLinkActive="bg-white/10 text-primary-400" class="block px-4 py-3 rounded-xl hover:bg-white/5 transition-all font-medium">System Admin</a>
        </nav>
        
        <div class="p-4 border-t border-white/10">
          <div class="flex items-center gap-3 px-2">
            <div class="w-10 h-10 rounded-full bg-gradient-to-tr from-primary-500 to-purple-500 border-2 border-white/20"></div>
            <div>
              <div class="text-sm font-semibold">Admin User</div>
              <div class="text-xs text-slate-400">System Architect</div>
            </div>
          </div>
        </div>
      </aside>

      <!-- Main Content -->
      <main class="flex-1 flex flex-col overflow-hidden relative">
        <header class="h-16 bg-white/80 backdrop-blur-md border-b flex items-center px-8 justify-between sticky top-0 z-20">
          <h2 class="text-xl font-semibold text-slate-800">Support Operations Center</h2>
          <div class="flex items-center space-x-6">
            <div class="flex items-center gap-2">
              <span class="relative flex h-3 w-3">
                <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span class="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
              </span>
              <span class="text-sm font-medium text-slate-600">RAG Engine Online</span>
            </div>
            <button class="w-10 h-10 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center transition-colors">
              🔔
            </button>
          </div>
        </header>
        
        <div class="flex-1 overflow-auto p-8 layout-content-area">
          <router-outlet></router-outlet>
        </div>
      </main>
    </div>
  `
})
export class AppComponent {}
