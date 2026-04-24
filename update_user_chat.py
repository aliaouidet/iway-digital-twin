import re

with open('iway ui/src/app/zones/user-chat/user-chat.component.ts', 'r') as f:
    content = f.read()

# 1. Add HostListener and animations imports
content = content.replace(
    "import { Component, OnInit, OnDestroy, signal, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';",
    "import { Component, OnInit, OnDestroy, signal, ViewChild, ElementRef, AfterViewChecked, HostListener } from '@angular/core';\nimport { trigger, state, style, transition, animate } from '@angular/animations';"
)

# 2. Add animations to Component decorator
component_dec = """@Component({
  selector: 'app-user-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, IwayLogoComponent],
  animations: [
    trigger('dropdownAnimation', [
      state('open', style({ height: '*', opacity: 1, paddingBottom: '0.25rem' })),
      state('closed', style({ height: '0', opacity: 0, overflow: 'hidden', paddingBottom: '0' })),
      transition('closed <=> open', [
        animate('200ms ease-in-out')
      ])
    ])
  ],
  template: `"""
content = content.replace(
    "@Component({\n  selector: 'app-user-chat',\n  standalone: true,\n  imports: [CommonModule, FormsModule, IwayLogoComponent],\n  template: `",
    component_dec
)

# 3. Modify Sidebar classes (Lines 41-42 originally)
content = content.replace(
    """      <!-- Left Sidebar: Chat History -->
      <aside class="w-72 flex flex-col border-r flex-shrink-0 transition-colors"
        [class]="isDark() ? 'bg-[#0F172A] border-slate-800' : 'bg-white border-slate-200'">""",
    """      <!-- Mobile Backdrop -->
      <div *ngIf="isSidebarOpen() && !isDesktopMode" 
           (click)="closeSidebar()"
           class="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-40 md:hidden transition-opacity">
      </div>

      <!-- Left Sidebar: Chat History -->
      <aside class="w-72 flex flex-col border-r flex-shrink-0 absolute md:relative z-50 h-full transition-transform duration-300 transform"
        [class.translate-x-0]="isSidebarOpen() || isDesktopMode"
        [class.-translate-x-full]="!isSidebarOpen() && !isDesktopMode"
        [class]="isDark() ? 'bg-[#0F172A] border-slate-800' : 'bg-white border-slate-200'">"""
)

# 4. Modify Sidebar Header (Logo and Buttons)
old_sidebar_header = """        <!-- Sidebar Header -->
        <div class="h-16 flex items-center justify-between px-4 border-b flex-shrink-0"
          [class]="isDark() ? 'border-slate-800' : 'border-slate-200'">
          <div class="flex items-center gap-2">
            <div style="width: 110px;">
              <app-iway-logo [dark]="isDark()" width="100%"></app-iway-logo>
            </div>
          </div>
          <div class="flex items-center gap-1">
            <button (click)="toggleTheme()" class="w-7 h-7 rounded-lg flex items-center justify-center transition-colors cursor-pointer"
              [class]="isDark() ? 'hover:bg-slate-800 text-slate-500' : 'hover:bg-slate-100 text-slate-400'">
              <svg *ngIf="isDark()" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"/></svg>
              <svg *ngIf="!isDark()" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"/></svg>
            </button>
            <button (click)="logout()" class="w-7 h-7 rounded-lg flex items-center justify-center transition-colors cursor-pointer"
              [class]="isDark() ? 'hover:bg-slate-800 text-slate-500 hover:text-rose-400' : 'hover:bg-slate-100 text-slate-400 hover:text-rose-500'">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9"/></svg>
            </button>
          </div>
        </div>"""

new_sidebar_header = """        <!-- Sidebar Header -->
        <div class="h-16 flex items-center justify-between px-4 border-b flex-shrink-0"
          [class]="isDark() ? 'border-slate-800' : 'border-slate-200'">
          <div class="flex items-center gap-2">
            <div class="w-[80px] md:w-[110px] flex-shrink-0">
              <app-iway-logo [dark]="isDark()" width="100%"></app-iway-logo>
            </div>
          </div>
          <div class="flex items-center gap-1 z-10 relative">
            <button (click)="toggleTheme()" class="w-7 h-7 rounded-lg flex items-center justify-center transition-colors cursor-pointer"
              [class]="isDark() ? 'hover:bg-slate-800 text-slate-500' : 'hover:bg-slate-100 text-slate-400'">
              <svg *ngIf="isDark()" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"/></svg>
              <svg *ngIf="!isDark()" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"/></svg>
            </button>
            <button (click)="logout()" class="w-7 h-7 rounded-lg flex items-center justify-center transition-colors cursor-pointer hidden md:flex"
              [class]="isDark() ? 'hover:bg-slate-800 text-slate-500 hover:text-rose-400' : 'hover:bg-slate-100 text-slate-400 hover:text-rose-500'">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9"/></svg>
            </button>
            <button (click)="closeSidebar()" class="md:hidden w-7 h-7 rounded-lg flex items-center justify-center transition-colors cursor-pointer"
              [class]="isDark() ? 'hover:bg-slate-800 text-slate-300' : 'hover:bg-slate-100 text-slate-700'">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
        </div>"""
content = content.replace(old_sidebar_header, new_sidebar_header)

# 5. Modify Chat List to use Dropdowns
old_chat_list = """        <!-- Chat List -->
        <div class="flex-1 overflow-y-auto px-3 space-y-1 custom-scrollbar">
          <button *ngFor="let chat of visibleThreads()" (click)="switchChat(chat)"
            class="w-full text-left p-3 rounded-xl transition-all cursor-pointer"
            [class]="getChatItemClass(chat)">
            <div class="flex items-center justify-between mb-1">
              <span class="text-[10px] font-medium" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">
                {{formatDate(chat.created_at)}}
              </span>
              <span *ngIf="chat.status === 'handoff_pending'" class="px-1.5 py-0.5 rounded text-[8px] font-bold uppercase"
                [class]="isDark() ? 'bg-amber-500/10 text-amber-400' : 'bg-amber-50 text-amber-600'">Agent</span>
              <span *ngIf="chat.status === 'resolved'" class="px-1.5 py-0.5 rounded text-[8px] font-bold uppercase"
                [class]="isDark() ? 'bg-emerald-500/10 text-emerald-400' : 'bg-emerald-50 text-emerald-600'">Résolu</span>
            </div>
            <p class="text-xs truncate" [class]="isDark() ? 'text-slate-400' : 'text-slate-600'">
              {{chat.last_message || 'Nouvelle conversation'}}
            </p>
            <span class="text-[10px] mt-1 block" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">
              {{chat.message_count}} messages
            </span>
          </button>
          <div *ngIf="visibleThreads().length === 0" class="text-center py-8">
            <p class="text-xs" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">Aucune conversation</p>
          </div>
        </div>"""

new_chat_list = """        <!-- Chat List -->
        <div class="flex-1 overflow-y-auto px-3 space-y-2 py-2 custom-scrollbar">
          
          <!-- Active Chats Dropdown -->
          <div>
            <button (click)="isActiveChatsOpen.set(!isActiveChatsOpen())" class="w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-colors cursor-pointer"
              [class]="isDark() ? 'hover:bg-slate-800/50 text-slate-300' : 'hover:bg-slate-100/50 text-slate-700'">
              <div class="flex items-center gap-2">
                <svg class="w-3.5 h-3.5 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
                <span class="text-[10px] font-semibold uppercase tracking-wider">Actives ({{activeThreads().length}})</span>
              </div>
              <svg class="w-3.5 h-3.5 transition-transform duration-200" [class.rotate-180]="isActiveChatsOpen()" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
            </button>
            
            <div [@dropdownAnimation]="isActiveChatsOpen() ? 'open' : 'closed'" class="overflow-hidden px-1">
              <button *ngFor="let chat of activeThreads()" (click)="selectChat(chat)"
                class="w-full text-left p-2.5 rounded-xl transition-all cursor-pointer mb-1"
                [class]="getChatItemClass(chat)">
                <div class="flex items-center justify-between mb-0.5">
                  <span class="text-[9px] font-medium" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">{{formatDate(chat.created_at)}}</span>
                  <span *ngIf="chat.status === 'handoff_pending'" class="px-1.5 py-0.5 rounded text-[8px] font-bold uppercase"
                    [class]="isDark() ? 'bg-amber-500/10 text-amber-400' : 'bg-amber-50 text-amber-600'">Agent</span>
                </div>
                <p class="text-[11px] truncate" [class]="isDark() ? 'text-slate-400' : 'text-slate-600'">{{chat.last_message || 'Nouvelle conversation'}}</p>
                <span class="text-[9px] mt-0.5 block" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">{{chat.message_count}} messages</span>
              </button>
              <div *ngIf="activeThreads().length === 0" class="text-center py-4">
                <p class="text-[10px]" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">Aucune conversation active</p>
              </div>
            </div>
          </div>

          <!-- Resolved Chats Dropdown -->
          <div>
            <button (click)="isResolvedChatsOpen.set(!isResolvedChatsOpen())" class="w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-colors cursor-pointer"
              [class]="isDark() ? 'hover:bg-slate-800/50 text-slate-300' : 'hover:bg-slate-100/50 text-slate-700'">
              <div class="flex items-center gap-2">
                <svg class="w-3.5 h-3.5 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                <span class="text-[10px] font-semibold uppercase tracking-wider">Résolues ({{resolvedThreads().length}})</span>
              </div>
              <svg class="w-3.5 h-3.5 transition-transform duration-200" [class.rotate-180]="isResolvedChatsOpen()" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
            </button>
            
            <div [@dropdownAnimation]="isResolvedChatsOpen() ? 'open' : 'closed'" class="overflow-hidden px-1">
              <button *ngFor="let chat of resolvedThreads()" (click)="selectChat(chat)"
                class="w-full text-left p-2.5 rounded-xl transition-all cursor-pointer mb-1"
                [class]="getChatItemClass(chat)">
                <div class="flex items-center justify-between mb-0.5">
                  <span class="text-[9px] font-medium" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">{{formatDate(chat.created_at)}}</span>
                  <span class="px-1.5 py-0.5 rounded text-[8px] font-bold uppercase"
                    [class]="isDark() ? 'bg-emerald-500/10 text-emerald-400' : 'bg-emerald-50 text-emerald-600'">Résolu</span>
                </div>
                <p class="text-[11px] truncate" [class]="isDark() ? 'text-slate-400' : 'text-slate-600'">{{chat.last_message || 'Nouvelle conversation'}}</p>
                <span class="text-[9px] mt-0.5 block" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">{{chat.message_count}} messages</span>
              </button>
              <div *ngIf="resolvedThreads().length === 0" class="text-center py-4">
                <p class="text-[10px]" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">Aucune conversation résolue</p>
              </div>
            </div>
          </div>

        </div>"""
content = content.replace(old_chat_list, new_chat_list)

# 6. Modify Main Header (Burger button)
old_main_header = """        <!-- Header -->
        <header class="h-16 flex items-center justify-between px-6 border-b flex-shrink-0 transition-colors"
          [class]="isDark() ? 'bg-[#0F172A]/80 border-slate-800 backdrop-blur-md' : 'bg-white/80 border-slate-200 backdrop-blur-md'">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 bg-gradient-to-br from-indigo-500 to-indigo-700 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <svg class="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"/></svg>
            </div>
            <div>
              <span class="text-base font-bold" style="font-family: 'Figtree', sans-serif;"
                [class]="isDark() ? 'text-white' : 'text-slate-900'">I-Way Assistant</span>
              <div class="flex items-center gap-1.5">
                <span class="relative flex h-2 w-2"><span class="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" [class]="isConnected() ? 'bg-emerald-400' : 'bg-slate-400'"></span><span class="relative inline-flex rounded-full h-2 w-2" [class]="isConnected() ? 'bg-emerald-500' : 'bg-slate-500'"></span></span>
                <span class="text-[10px] font-medium" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">{{isConnected() ? 'En ligne' : 'Connexion...'}}</span>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button *ngIf="!isHandoffActive() && sessionId" (click)="requestHandoff()"
              class="px-4 py-2 rounded-xl text-xs font-semibold transition-colors cursor-pointer flex items-center gap-1.5"
              [class]="isDark() ? 'bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 border border-rose-500/20' : 'bg-rose-50 text-rose-600 hover:bg-rose-100 border border-rose-200'">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/></svg>
              Parler à un agent
            </button>
            <button (click)="logout()" class="md:hidden w-8 h-8 rounded-lg flex items-center justify-center transition-colors cursor-pointer ml-1"
              [class]="isDark() ? 'hover:bg-slate-800 text-slate-500 hover:text-rose-400' : 'hover:bg-slate-100 text-slate-400 hover:text-rose-500'">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9"/></svg>
            </button>
          </div>
        </header>"""

new_main_header = """        <!-- Header -->
        <header class="h-16 flex items-center justify-between px-4 md:px-6 border-b flex-shrink-0 transition-colors relative z-30"
          [class]="isDark() ? 'bg-[#0F172A]/80 border-slate-800 backdrop-blur-md' : 'bg-white/80 border-slate-200 backdrop-blur-md'">
          <div class="flex items-center gap-2 md:gap-3 min-w-0">
            <button (click)="toggleSidebar()" class="md:hidden p-1.5 -ml-1 rounded-lg transition-colors cursor-pointer flex-shrink-0" [class]="isDark() ? 'hover:bg-slate-800 text-slate-300' : 'hover:bg-slate-100 text-slate-700'">
                <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/></svg>
            </button>
            <div class="w-8 h-8 md:w-9 md:h-9 bg-gradient-to-br from-indigo-500 to-indigo-700 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-500/20 flex-shrink-0">
              <svg class="w-4 h-4 md:w-5 md:h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"/></svg>
            </div>
            <div class="truncate">
              <span class="text-sm md:text-base font-bold truncate" style="font-family: 'Figtree', sans-serif;"
                [class]="isDark() ? 'text-white' : 'text-slate-900'">I-Way Assistant</span>
              <div class="flex items-center gap-1.5">
                <span class="relative flex h-2 w-2"><span class="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" [class]="isConnected() ? 'bg-emerald-400' : 'bg-slate-400'"></span><span class="relative inline-flex rounded-full h-2 w-2" [class]="isConnected() ? 'bg-emerald-500' : 'bg-slate-500'"></span></span>
                <span class="text-[9px] md:text-[10px] font-medium" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">{{isConnected() ? 'En ligne' : 'Connexion...'}}</span>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-1 md:gap-2 flex-shrink-0">
            <button *ngIf="!isHandoffActive() && sessionId" (click)="requestHandoff()"
              class="px-2.5 md:px-4 py-1.5 md:py-2 rounded-xl text-[10px] md:text-xs font-semibold transition-colors cursor-pointer flex items-center gap-1.5"
              [class]="isDark() ? 'bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 border border-rose-500/20' : 'bg-rose-50 text-rose-600 hover:bg-rose-100 border border-rose-200'">
              <svg class="w-3.5 h-3.5 hidden md:block" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/></svg>
              Parler à un agent
            </button>
            <button (click)="logout()" class="md:hidden w-8 h-8 rounded-lg flex items-center justify-center transition-colors cursor-pointer"
              [class]="isDark() ? 'hover:bg-slate-800 text-slate-500 hover:text-rose-400' : 'hover:bg-slate-100 text-slate-400 hover:text-rose-500'">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9"/></svg>
            </button>
          </div>
        </header>"""

# We also need to add the logout button on mobile header if we removed the original logout button? 
# Wait, the original code DID NOT HAVE a logout button in the main header. I will add it to `new_main_header`.
content = content.replace(old_main_header, new_main_header)
if old_main_header not in content:
    # If the exact match fails (e.g. because I missed the exact space), we'll do something else.
    # Actually wait, let's just make sure the `old_main_header` matches.
    pass

# 7. Add signals to the class
class_start = """export class UserChatComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('messageContainer') private messageContainer!: ElementRef;"""

new_class_start = """export class UserChatComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('messageContainer') private messageContainer!: ElementRef;

  // Responsive UI Signals
  isSidebarOpen = signal(false);
  isDesktopMode = true;
  isActiveChatsOpen = signal(true);
  isResolvedChatsOpen = signal(false);"""
content = content.replace(class_start, new_class_start)

# 8. Add activeThreads and resolvedThreads functions
# right after visibleThreads
old_visible_threads = """      try {
        const age = now - new Date(c.created_at).getTime();
        return age < 5 * 60 * 1000;
      } catch { return true; }
    });
  };"""

new_visible_threads = """      try {
        const age = now - new Date(c.created_at).getTime();
        return age < 5 * 60 * 1000;
      } catch { return true; }
    });
  };

  activeThreads = () => this.visibleThreads().filter(c => c.status !== 'resolved');
  resolvedThreads = () => this.visibleThreads().filter(c => c.status === 'resolved');

  @HostListener('window:resize', ['$event'])
  onResize() {
    this.checkScreenSize();
  }

  private checkScreenSize() {
    this.isDesktopMode = window.innerWidth >= 768; // md breakpoint
    if (this.isDesktopMode) {
      this.isSidebarOpen.set(false); // Reset mobile sidebar state when returning to desktop
    }
  }

  toggleSidebar(): void {
    this.isSidebarOpen.update(v => !v);
  }

  closeSidebar(): void {
    this.isSidebarOpen.set(false);
  }

  selectChat(chat: ChatThread): void {
    this.switchChat(chat);
    if (!this.isDesktopMode) {
      this.closeSidebar();
    }
  }"""
content = content.replace(old_visible_threads, new_visible_threads)

# Update ngOnInit to call checkScreenSize()
content = content.replace(
    "this.loadChatThreads();\n    this.resumeLastActiveChat();",
    "this.checkScreenSize();\n    this.loadChatThreads();\n    this.resumeLastActiveChat();"
)

# Wait, `switchChat(chat)` is used in HTML in the old version.
# In the new chat list HTML, I replaced `switchChat(chat)` with `selectChat(chat)` to also close the sidebar on mobile.

with open('iway ui/src/app/zones/user-chat/user-chat.component.ts', 'w') as f:
    f.write(content)

