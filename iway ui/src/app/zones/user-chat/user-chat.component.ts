import { Component, OnInit, OnDestroy, signal, ViewChild, ElementRef, AfterViewChecked, HostListener } from '@angular/core';
import { trigger, state, style, transition, animate } from '@angular/animations';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { retry, timer, Subject, takeUntil, Subscription, EMPTY } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { AuthService } from '../../core/services/auth.service';
import { ThemeService } from '../../core/services/theme.service';
import { ToastService } from '../../core/services/toast.service';
import { IwayLogoComponent } from '../../shared/components/iway-logo.component';

interface ChatMessage {
  role: 'user' | 'assistant' | 'agent' | 'system';
  content: string;
  timestamp?: string;
  isStreaming?: boolean;
  is_handoff_ai?: boolean;
  confidence?: number;
}

interface ChatThread {
  id: string;
  status: string;
  created_at: string;
  message_count: number;
  last_message: string;
  reason: string | null;
  has_agent: boolean;
}

@Component({
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
  template: `
    <div class="h-screen flex transition-colors duration-300"
      [class]="isDark() ? 'bg-[#020617]' : 'bg-slate-50'">

      <!-- Mobile Backdrop -->
      <div *ngIf="isSidebarOpen() && !isDesktopMode" 
           (click)="closeSidebar()"
           class="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-40 lg:hidden transition-opacity">
      </div>

      <!-- Left Sidebar: Chat History -->
      <aside class="w-72 flex flex-col border-r flex-shrink-0 absolute lg:relative z-50 h-full transition-transform duration-300 transform"
        [class.translate-x-0]="isSidebarOpen() || isDesktopMode"
        [class.-translate-x-full]="!isSidebarOpen() && !isDesktopMode"
        [class]="isDark() ? 'bg-[#0F172A] border-slate-800' : 'bg-white border-slate-200'">
        <!-- Sidebar Header -->
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
        </div>

        <!-- New Chat Button -->
        <div class="px-3 py-3">
          <button (click)="createNewChat()" class="w-full py-2.5 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center justify-center gap-2"
            [class]="isDark() ? 'bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500/20 border border-indigo-500/20' : 'bg-indigo-50 text-indigo-600 hover:bg-indigo-100 border border-indigo-200'">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.5v15m7.5-7.5h-15"/></svg>
            Nouvelle conversation
          </button>
        </div>

        <!-- Chat List -->
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

        </div>
      </aside>

      <!-- Main Chat Panel -->
      <main class="flex-1 flex flex-col">
        <!-- Header -->
        <header class="h-16 flex items-center justify-between px-4 md:px-6 border-b flex-shrink-0 transition-colors relative z-30"
          [class]="isDark() ? 'bg-[#0F172A]/80 border-slate-800 backdrop-blur-md' : 'bg-white/80 border-slate-200 backdrop-blur-md'">
          <div class="flex items-center gap-2 md:gap-3 min-w-0">
            <button (click)="toggleSidebar()" class="lg:hidden p-1.5 -ml-1 rounded-lg transition-colors cursor-pointer flex-shrink-0" [class]="isDark() ? 'hover:bg-slate-800 text-slate-300' : 'hover:bg-slate-100 text-slate-700'">
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
            <button (click)="logout()" class="lg:hidden w-8 h-8 rounded-lg flex items-center justify-center transition-colors cursor-pointer"
              [class]="isDark() ? 'hover:bg-slate-800 text-slate-500 hover:text-rose-400' : 'hover:bg-slate-100 text-slate-400 hover:text-rose-500'">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9"/></svg>
            </button>
          </div>
        </header>

        <!-- Handoff Banner (keep chatting) -->
        <div *ngIf="isHandoffPending()" class="px-6 py-3 flex items-center gap-3 border-b animate-fade-in"
          [class]="isDark() ? 'bg-amber-500/10 border-amber-500/20' : 'bg-amber-50 border-amber-200'">
          <div class="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" [class]="isDark() ? 'bg-amber-500/20' : 'bg-amber-100'">
            <svg class="w-4 h-4 animate-pulse" [class]="isDark() ? 'text-amber-400' : 'text-amber-600'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          </div>
          <div>
            <p class="text-xs font-semibold" [class]="isDark() ? 'text-amber-300' : 'text-amber-800'">
              Un agent va vous rejoindre bientôt
            </p>
            <p class="text-[10px]" [class]="isDark() ? 'text-amber-400/70' : 'text-amber-600'">
              Vous pouvez continuer à poser des questions en attendant.
            </p>
          </div>
        </div>

        <!-- Agent Joined Banner -->
        <div *ngIf="agentName()" class="px-6 py-3 flex items-center gap-3 border-b animate-fade-in"
          [class]="isDark() ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-emerald-50 border-emerald-200'">
          <div class="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" [class]="isDark() ? 'bg-emerald-500/20' : 'bg-emerald-100'">
            <svg class="w-4 h-4" [class]="isDark() ? 'text-emerald-400' : 'text-emerald-600'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          </div>
          <div>
            <p class="text-xs font-semibold" [class]="isDark() ? 'text-emerald-300' : 'text-emerald-800'">
              {{agentName()}} a rejoint la conversation
            </p>
            <p class="text-[10px]" [class]="isDark() ? 'text-emerald-400/70' : 'text-emerald-600'">
              Vous discutez maintenant avec un agent. Il a lu le résumé de votre conversation.
            </p>
          </div>
        </div>

        <!-- Messages -->
        <div #messageContainer class="flex-1 overflow-y-auto px-4 py-6 space-y-4 custom-scrollbar">
          <!-- Welcome (no active session yet) -->
          <div *ngIf="messages().length === 0" class="flex flex-col items-center justify-center h-full text-center px-4">
            <div class="w-16 h-16 rounded-2xl flex items-center justify-center mb-5"
              [class]="isDark() ? 'bg-indigo-500/10' : 'bg-indigo-50'">
              <svg class="w-8 h-8" [class]="isDark() ? 'text-indigo-400' : 'text-indigo-500'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8.625 9.75a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 01.778-.332 48.294 48.294 0 005.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z"/></svg>
            </div>
            <h2 class="text-xl font-bold mb-2" style="font-family: 'Figtree', sans-serif;"
              [class]="isDark() ? 'text-white' : 'text-slate-900'">Bienvenue sur I-Way Support</h2>
            <p class="text-sm max-w-sm" [class]="isDark() ? 'text-slate-500' : 'text-slate-500'">
              Posez vos questions sur la couverture, les remboursements ou toute question d'assurance.
            </p>
            <div class="flex flex-wrap gap-2 mt-6 justify-center">
              <button *ngFor="let q of quickQuestions" (click)="sendQuickQuestion(q)"
                class="px-3.5 py-2 rounded-xl text-xs font-medium transition-colors cursor-pointer"
                [class]="isDark() ? 'bg-slate-800 hover:bg-slate-700 text-slate-400 border border-slate-700' : 'bg-white hover:bg-slate-50 text-slate-600 border border-slate-200 shadow-sm'">
                {{q}}
              </button>
            </div>
          </div>

          <!-- Message Bubbles -->
          <div *ngFor="let msg of messages(); trackBy: trackByIdx">
            <!-- System Message -->
            <div *ngIf="msg.role === 'system'" class="flex justify-center">
              <div class="px-4 py-2 rounded-full text-xs font-medium"
                [class]="isDark() ? 'bg-slate-800/50 text-slate-500' : 'bg-slate-100 text-slate-500'">
                {{msg.content}}
              </div>
            </div>
            <!-- User Message -->
            <div *ngIf="msg.role === 'user'" class="flex justify-end">
              <div class="max-w-[75%] px-4 py-3 rounded-2xl rounded-br-md text-sm bg-indigo-600 text-white">
                {{msg.content}}
              </div>
            </div>
            <!-- AI / Agent Message -->
            <div *ngIf="msg.role === 'assistant' || msg.role === 'agent'" class="flex justify-start gap-2.5">
              <div class="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-1"
                [class]="msg.role === 'agent'
                  ? (isDark() ? 'bg-amber-500/20' : 'bg-amber-100')
                  : msg.is_handoff_ai
                    ? (isDark() ? 'bg-orange-500/10' : 'bg-orange-50')
                    : (isDark() ? 'bg-indigo-500/10' : 'bg-indigo-50')">
                <svg *ngIf="msg.role === 'assistant' && !msg.is_handoff_ai" class="w-3.5 h-3.5" [class]="isDark() ? 'text-indigo-400' : 'text-indigo-500'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/></svg>
                <svg *ngIf="msg.is_handoff_ai" class="w-3.5 h-3.5" [class]="isDark() ? 'text-orange-400' : 'text-orange-500'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                <svg *ngIf="msg.role === 'agent'" class="w-3.5 h-3.5" [class]="isDark() ? 'text-amber-400' : 'text-amber-600'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/></svg>
              </div>
              <div>
                <!-- Handoff AI badge -->
                <div *ngIf="msg.is_handoff_ai" class="mb-1">
                  <span class="px-2 py-0.5 rounded-full text-[9px] font-semibold"
                    [class]="isDark() ? 'bg-orange-500/10 text-orange-400 border border-orange-500/20' : 'bg-orange-50 text-orange-600 border border-orange-200'">
                    ⏳ En attendant l'agent
                  </span>
                </div>
                <div class="max-w-[75%] px-4 py-3 rounded-2xl rounded-bl-md text-sm"
                  [class]="msg.is_handoff_ai
                    ? (isDark() ? 'bg-orange-500/5 border border-orange-500/20 text-orange-200' : 'bg-orange-50 border border-orange-200 text-orange-900')
                    : (isDark() ? 'bg-[#0F172A] border border-slate-800 text-slate-300' : 'bg-white border border-slate-200 text-slate-700 shadow-sm')">
                  {{msg.content}}<span *ngIf="msg.isStreaming" class="inline-block w-1.5 h-4 ml-0.5 rounded-sm animate-pulse" [class]="isDark() ? 'bg-indigo-400' : 'bg-indigo-500'"></span>
                </div>
              </div>
            </div>
          </div>

          <!-- Thinking indicator -->
          <div *ngIf="isThinking()" class="flex justify-start gap-2.5">
            <div class="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
              [class]="isDark() ? 'bg-indigo-500/10' : 'bg-indigo-50'">
              <svg class="w-3.5 h-3.5" [class]="isDark() ? 'text-indigo-400' : 'text-indigo-500'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/></svg>
            </div>
            <div class="px-4 py-3 rounded-2xl rounded-bl-md"
              [class]="isDark() ? 'bg-[#0F172A] border border-slate-800' : 'bg-white border border-slate-200 shadow-sm'">
              <div class="flex items-center gap-3">
                <div class="flex gap-1">
                  <span class="w-2 h-2 rounded-full animate-bounce" [class]="isDark() ? 'bg-indigo-400' : 'bg-indigo-500'" style="animation-delay: 0ms"></span>
                  <span class="w-2 h-2 rounded-full animate-bounce" [class]="isDark() ? 'bg-indigo-400' : 'bg-indigo-500'" style="animation-delay: 150ms"></span>
                  <span class="w-2 h-2 rounded-full animate-bounce" [class]="isDark() ? 'bg-indigo-400' : 'bg-indigo-500'" style="animation-delay: 300ms"></span>
                </div>
                <span *ngIf="thinkingStatus()" class="text-[10px] font-medium animate-pulse" [class]="isDark() ? 'text-indigo-400/70' : 'text-indigo-500/70'">
                  {{thinkingStatus()}}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- CSAT Feedback Widget -->
        <div *ngIf="isSessionResolved() && !feedbackGiven()" class="px-4 py-4 border-t flex-shrink-0 transition-all"
          [class]="isDark() ? 'bg-indigo-500/5 border-indigo-500/20' : 'bg-indigo-50 border-indigo-200'">
          <div class="max-w-3xl mx-auto">
            <div *ngIf="!showFeedbackComment()" class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <svg class="w-4 h-4" [class]="isDark() ? 'text-indigo-400' : 'text-indigo-500'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z"/></svg>
                <span class="text-xs font-semibold" [class]="isDark() ? 'text-indigo-300' : 'text-indigo-700'">Cette conversation vous a-t-elle été utile ?</span>
              </div>
              <div class="flex items-center gap-2">
                <button (click)="submitFeedback('positive')" class="px-4 py-2 rounded-xl text-xs font-semibold cursor-pointer transition-all flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
                  [class]="isDark() ? 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20' : 'bg-emerald-50 text-emerald-600 hover:bg-emerald-100 border border-emerald-200'">
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6.633 10.5c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 012.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 00.322-1.672V3a.75.75 0 01.75-.75A2.25 2.25 0 0116.5 4.5c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 01-2.649 7.521c-.388.482-.987.729-1.605.729H13.48c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 00-1.423-.23H5.904M14.25 9h2.25M5.904 18.75c.083.205.173.405.27.602.197.4-.078.898-.523.898h-.908c-.889 0-1.713-.518-1.972-1.368a12 12 0 01-.521-3.507c0-1.553.295-3.036.831-4.398C3.387 10.203 4.167 9.75 5 9.75h1.053c.472 0 .745.556.5.96a8.958 8.958 0 00-1.302 4.665c0 1.194.232 2.333.654 3.375z"/></svg>
                  Oui
                </button>
                <button (click)="showFeedbackComment.set(true); feedbackRating = 'negative'" class="px-4 py-2 rounded-xl text-xs font-semibold cursor-pointer transition-all flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-rose-500/50"
                  [class]="isDark() ? 'bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 border border-rose-500/20' : 'bg-rose-50 text-rose-600 hover:bg-rose-100 border border-rose-200'">
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7.5 15h2.25m8.024-9.75c.011.05.028.1.052.148.591 1.2.924 2.55.924 3.977a8.96 8.96 0 01-.999 4.125m.023-8.25c-.076-.365.183-.75.575-.75h.908c.889 0 1.713.518 1.972 1.368.339 1.11.521 2.287.521 3.507 0 1.553-.295 3.036-.831 4.398-.306.774-1.086 1.227-1.918 1.227h-1.053c-.472 0-.745-.556-.5-.96a8.95 8.95 0 00.303-.54m.023-8.25H16.48a4.5 4.5 0 01-1.423-.23l-3.114-1.04a4.5 4.5 0 00-1.423-.23H6.504c-.618 0-1.217.247-1.605.729A11.95 11.95 0 002.25 12c0 .434.023.863.068 1.285C2.427 14.306 3.346 15 4.372 15h3.126c.618 0 .991.724.725 1.282A7.471 7.471 0 007.5 19.5a2.25 2.25 0 002.25 2.25.75.75 0 00.75-.75v-.633c0-.573.11-1.14.322-1.672.304-.76.93-1.33 1.653-1.715a9.04 9.04 0 002.86-2.4c.498-.634 1.226-1.08 2.032-1.08h.384"/></svg>
                  Non
                </button>
              </div>
            </div>
            <!-- Comment input for negative feedback -->
            <div *ngIf="showFeedbackComment()" class="space-y-3">
              <p class="text-xs font-semibold" [class]="isDark() ? 'text-rose-300' : 'text-rose-700'">Qu'est-ce qui pourrait être amélioré ?</p>
              <textarea [(ngModel)]="feedbackComment" rows="2" placeholder="Votre commentaire (optionnel)..."
                class="w-full px-3 py-2 rounded-lg text-xs transition-all focus:outline-none focus:ring-1 focus:ring-indigo-500/50 resize-none"
                [class]="isDark() ? 'bg-slate-800/50 border border-slate-700 text-white placeholder-slate-500' : 'bg-white border border-slate-200 text-slate-900 placeholder-slate-400'"></textarea>
              <div class="flex gap-2">
                <button (click)="submitFeedback('negative')" class="px-4 py-2 rounded-lg text-[10px] font-semibold cursor-pointer transition-colors bg-rose-600 hover:bg-rose-500 text-white focus:outline-none focus:ring-2 focus:ring-rose-500/50">Envoyer</button>
                <button (click)="showFeedbackComment.set(false)" class="px-4 py-2 rounded-lg text-[10px] font-semibold cursor-pointer transition-colors" [class]="isDark() ? 'bg-slate-800 text-slate-400' : 'bg-white text-slate-600 border border-slate-200'">Annuler</button>
              </div>
            </div>
            <!-- Thank you message -->
          </div>
        </div>

        <!-- Thank you after feedback -->
        <div *ngIf="feedbackGiven()" class="px-4 py-3 border-t flex-shrink-0 text-center"
          [class]="isDark() ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-emerald-50 border-emerald-200'">
          <p class="text-xs font-semibold" [class]="isDark() ? 'text-emerald-400' : 'text-emerald-700'">Merci pour votre retour !</p>
        </div>

        <!-- Input -->
        <div *ngIf="!isSessionResolved()" class="px-4 py-4 border-t flex-shrink-0 transition-colors"
          [class]="isDark() ? 'bg-[#0F172A]/60 border-slate-800' : 'bg-white border-slate-200'">
          <form (ngSubmit)="sendMessage()" class="flex items-end gap-3 max-w-3xl mx-auto">
            <div class="flex-1 relative">
              <textarea [(ngModel)]="newMessage" name="msg" rows="1"
                placeholder="Écrivez votre message..."
                class="w-full px-4 py-3 rounded-xl text-sm transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500/50 resize-none"
                [class]="isDark() ? 'bg-slate-800/50 border border-slate-700 text-white placeholder-slate-500' : 'bg-slate-50 border border-slate-200 text-slate-900 placeholder-slate-400'"
                (keydown.enter)="$any($event).shiftKey ? null : onEnter($event)"></textarea>
            </div>
            <button type="submit" [disabled]="!newMessage.trim()"
              class="w-11 h-11 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 rounded-xl flex items-center justify-center text-white transition-all cursor-pointer disabled:cursor-not-allowed flex-shrink-0">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"/></svg>
            </button>
          </form>
        </div>
      </main>
    </div>
  `
})
export class UserChatComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('messageContainer') private messageContainer!: ElementRef;

  // Responsive UI Signals
  isSidebarOpen = signal(false);
  isDesktopMode = true;
  isActiveChatsOpen = signal(true);
  isResolvedChatsOpen = signal(false);

  messages = signal<ChatMessage[]>([]);
  chatThreads = signal<ChatThread[]>([]);
  newMessage = '';
  isConnected = signal(false);
  isThinking = signal(false);
  thinkingStatus = signal('');
  isHandoffActive = signal(false);
  isHandoffPending = signal(false);
  agentName = signal('');
  isSessionResolved = signal(false);

  // CSAT Feedback
  feedbackGiven = signal(false);
  showFeedbackComment = signal(false);
  feedbackRating = 'positive';
  feedbackComment = '';

  sessionId = '';
  private socket$: WebSocketSubject<any> | null = null;
  private streamingContent = '';
  private destroy$ = new Subject<void>();
  private pingSubscription: Subscription | null = null;
  private pendingMessage: string | null = null;  // Message waiting for WS to connect

  quickQuestions = [
    'Plafond soins dentaires ?',
    'Délai de remboursement ?',
    'Prime de naissance ?',
    'Numéro urgences ?',
  ];

  constructor(
    private authService: AuthService,
    private themeService: ThemeService,
    private http: HttpClient,
    private router: Router,
    private toastService: ToastService
  ) { }

  isDark = () => this.themeService.isDark();
  toggleTheme = () => this.themeService.toggleTheme();

  ngOnInit(): void {
    this.checkScreenSize();
    this.loadChatThreads();
    this.resumeLastActiveChat();
  }

  ngAfterViewChecked(): void {
    this.scrollToBottom();
  }

  // ─── Multi-Chat ───

  loadChatThreads(): void {
    this.http.get<ChatThread[]>(`${environment.apiUrl}/api/v1/sessions/user-chats`).subscribe({
      next: (chats) => this.chatThreads.set(chats),
      error: () => { }
    });
  }

  /** Filter: hide empty sessions older than 5 minutes */
  visibleThreads = () => {
    const now = Date.now();
    return this.chatThreads().filter(c => {
      if (c.message_count > 0) return true;
      // Keep empty sessions that are less than 5 min old (user might still be typing)
      try {
        const age = now - new Date(c.created_at).getTime();
        return age < 5 * 60 * 1000;
      } catch { return true; }
    });
  };

  activeThreads = () => this.visibleThreads().filter(c => c.status !== 'resolved');
  resolvedThreads = () => this.visibleThreads().filter(c => c.status === 'resolved');

  @HostListener('window:resize')
  onResize() {
    this.checkScreenSize();
  }

  private checkScreenSize() {
    this.isDesktopMode = window.innerWidth >= 1024; // lg breakpoint // md breakpoint
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
  }

  /**
   * On page load: resume the most recent active chat instead of creating a new one.
   * If no active chats exist, just show the welcome screen.
   */
  resumeLastActiveChat(): void {
    this.http.get<ChatThread[]>(`${environment.apiUrl}/api/v1/sessions/user-chats`).subscribe({
      next: (chats) => {
        this.chatThreads.set(chats);
        // Find the most recent non-resolved chat
        const active = chats.find(c => c.status !== 'resolved' && c.message_count > 0);
        if (active) {
          this.switchChat(active);
        }
        // If no active chat, just show the welcome screen — no session created
      },
      error: () => { }
    });
  }

  createNewChat(): void {
    // Disconnect current
    this.socket$?.complete();
    this.socket$ = null;
    this.messages.set([]);
    this.isHandoffActive.set(false);
    this.isHandoffPending.set(false);
    this.agentName.set('');
    this.isSessionResolved.set(false);
    this.streamingContent = '';
    this.sessionId = '';

    // Don't create a backend session yet!
    // It will be created lazily when the user sends their first message.
    // This prevents empty ghost sessions on every button click.
  }

  switchChat(chat: ChatThread): void {
    console.log(`[UserChat] switchChat called: chat.id=${chat.id}, current sessionId=${this.sessionId}`);
    if (chat.id === this.sessionId) return;

    // Disconnect current
    this.socket$?.complete();
    this.socket$ = null;
    this.streamingContent = '';
    this.isThinking.set(false);
    this.agentName.set('');

    this.sessionId = chat.id;
    this.isHandoffActive.set(chat.status === 'handoff_pending' || chat.status === 'agent_connected');
    this.isHandoffPending.set(chat.status === 'handoff_pending');
    this.isSessionResolved.set(chat.status === 'resolved');

    // Connect to existing session
    this.connectWebSocket();
  }

  getChatItemClass(chat: ChatThread): string {
    const active = chat.id === this.sessionId;
    if (this.isDark()) {
      if (active) return 'bg-indigo-500/10 border border-indigo-500/30';
      return 'hover:bg-slate-800/50 border border-transparent';
    } else {
      if (active) return 'bg-indigo-50 border border-indigo-200';
      return 'hover:bg-slate-50 border border-transparent';
    }
  }

  // ─── WebSocket ───

  private connectWebSocket(): void {
    // Clean up existing connection
    this.stopPing();
    if (this.socket$ && !this.socket$.closed) {
      this.socket$.complete();
    }

    const token = this.authService.getToken() || '';
    const wsUrl = `${environment.wsUrl.replace('/events', '')}/chat/${this.sessionId}?token=${token}`;

    this.socket$ = webSocket({
      url: wsUrl,
      deserializer: (e) => JSON.parse(e.data),
      openObserver: {
        next: () => {
          console.log('[UserChat WS] Connection opened, sending user_connect');
          // Send user_connect AFTER the WS is confirmed open
          this.socket$!.next({ type: 'user_connect' });
          // Start heartbeat
          this.startPing();
          // Flush any pending message that was waiting for connection
          if (this.pendingMessage) {
            const msg = this.pendingMessage;
            this.pendingMessage = null;
            setTimeout(() => {
              this.socket$?.next({ type: 'user_message', content: msg });
            }, 300);
          }
        }
      },
      closeObserver: {
        next: () => {
          console.log('[UserChat WS] Connection closed');
          this.isConnected.set(false);
          this.stopPing();
        }
      }
    });

    this.socket$.pipe(
      retry({
        count: 5,
        delay: (error, retryCount) => {
          const delayMs = Math.min(2000 * Math.pow(2, retryCount - 1), 30000);
          console.log(`[UserChat WS] Reconnecting in ${delayMs}ms (attempt ${retryCount})...`);
          return timer(delayMs);
        },
        resetOnSuccess: true,
      }),
      catchError(err => {
        console.error('[UserChat WS] Fatal error:', err);
        this.isConnected.set(false);
        return EMPTY;
      }),
      takeUntil(this.destroy$)
    ).subscribe({
      next: (msg) => this.handleWsMessage(msg),
      error: (err) => { console.error('[UserChat WS] Stream error:', err); this.isConnected.set(false); },
      complete: () => this.isConnected.set(false),
    });
  }

  /** Start periodic PING heartbeat to keep the connection alive */
  private startPing(): void {
    this.stopPing();
    this.pingSubscription = timer(25000, 25000).pipe(
      takeUntil(this.destroy$)
    ).subscribe(() => {
      if (this.socket$ && !this.socket$.closed) {
        this.socket$.next({ type: 'PING' });
      }
    });
  }

  /** Stop the heartbeat timer */
  private stopPing(): void {
    if (this.pingSubscription) {
      this.pingSubscription.unsubscribe();
      this.pingSubscription = null;
    }
  }

  private handleWsMessage(msg: any): void {
    switch (msg.type) {
      case 'connected':
        console.log('[UserChat WS] ← connected event received');
        this.isConnected.set(true);
        break;
      case 'history':
        console.log(`[UserChat WS] ← history: ${msg.messages?.length ?? 0} messages`);
        if (msg.messages?.length) {
          this.messages.set(msg.messages.map((m: any) => ({
            role: m.role,
            content: m.content,
            timestamp: m.timestamp,
            is_handoff_ai: m.is_handoff_ai,
            confidence: m.confidence,
          })));
        }
        break;
      case 'thinking':
        this.isThinking.set(true);
        this.thinkingStatus.set(msg.status || '');
        break;
      case 'ai_token':
        this.isThinking.set(false);
        this.thinkingStatus.set('');
        this.streamingContent += msg.token;
        console.log(`[UserChat WS] ← ai_token (total chars: ${this.streamingContent.length})`);
        // Update or create streaming message
        this.messages.update(msgs => {
          const lastIdx = msgs.length - 1;
          const last = msgs[lastIdx];
          if (last?.isStreaming) {
            // Update existing streaming message
            const copy = [...msgs];
            copy[lastIdx] = { ...last, content: this.streamingContent };
            return copy;
          } else {
            // Create new streaming message
            return [...msgs, { role: 'assistant', content: this.streamingContent, isStreaming: true }];
          }
        });
        break;
      case 'ai_done':
        console.log(`[UserChat WS] ← ai_done (streamingContent len: ${this.streamingContent.length}, lastMsg streaming: ${this.messages()[this.messages().length-1]?.isStreaming})`);
        this.isThinking.set(false);
        this.thinkingStatus.set('');
        const updated = this.messages();
        const lastMsg = updated[updated.length - 1];
        if (lastMsg?.isStreaming) {
          // Happy path: finalize the streaming message
          this.messages.set([...updated.slice(0, -1), {
            ...lastMsg,
            isStreaming: false,
            is_handoff_ai: msg.is_handoff_ai || false,
            confidence: msg.confidence,
          }]);
        } else if (msg.text) {
          // Fallback: tokens were lost (WS reconnect, timing issue)
          // Use the full response text from ai_done payload
          console.warn('[UserChat WS] ⚠ Tokens lost — using ai_done text fallback');
          this.messages.update(msgs => [...msgs, {
            role: 'assistant',
            content: msg.text,
            is_handoff_ai: msg.is_handoff_ai || false,
            confidence: msg.confidence,
          }]);
        }
        this.streamingContent = '';
        this.loadChatThreads(); // Update sidebar
        break;
      case 'handoff_started':
        this.isHandoffActive.set(true);
        this.isHandoffPending.set(true);
        this.isThinking.set(false);
        // DON'T disable input — user can keep chatting!
        this.messages.update(m => [...m, {
          role: 'system',
          content: msg.keep_chatting
            ? 'Un agent va vous rejoindre bientôt. Vous pouvez continuer à poser des questions.'
            : (msg.reason || 'Transfert vers un spécialiste...')
        }]);
        this.loadChatThreads();
        break;
      case 'agent_joined':
        this.agentName.set(msg.agent_name || 'Agent');
        this.isHandoffPending.set(false);
        this.toastService.show(`${msg.agent_name || 'Un agent'} a rejoint la conversation`, 'info');
        this.messages.update(m => [...m, {
          role: 'system',
          content: msg.message || `${msg.agent_name} a rejoint la conversation.`
        }]);
        this.loadChatThreads();
        break;
      case 'agent_message':
        this.messages.update(m => [...m, { role: 'agent', content: msg.content, timestamp: msg.timestamp }]);
        break;
      case 'session_resolved':
        this.toastService.show('Session résolue. Merci pour votre patience!', 'success');
        this.messages.update(m => [...m, { role: 'system', content: 'Session résolue. Merci d\'avoir contacté I-Way.' }]);
        this.isSessionResolved.set(true);
        this.loadChatThreads();
        break;
      case 'PONG':
        // Heartbeat acknowledged — connection is alive
        break;
    }
  }

  sendMessage(): void {
    if (!this.newMessage.trim()) return;
    const content = this.newMessage.trim();
    this.newMessage = '';

    // Lazy session creation: if no session exists yet, create one first
    if (!this.sessionId) {
      this.messages.update(m => [...m, { role: 'user', content }]);
      this.isThinking.set(true);
      this.thinkingStatus.set('Création de la session...');
      this.http.post<{ session_id: string }>(`${environment.apiUrl}/api/v1/sessions/create`, {}).subscribe({
        next: (res) => {
          this.sessionId = res.session_id;
          this.pendingMessage = content;  // Queue the message for after WS connects
          this.connectWebSocket();
          this.loadChatThreads();
        },
        error: (err) => {
          console.error('Failed to create session:', err);
          this.isThinking.set(false);
          this.toastService.show('Erreur de connexion. Veuillez réessayer.', 'error');
        }
      });
      return;
    }

    // Normal path: session already exists
    this.messages.update(m => [...m, { role: 'user', content }]);
    this.socket$?.next({ type: 'user_message', content });
  }

  sendQuickQuestion(q: string): void {
    this.newMessage = q;
    this.sendMessage();
  }

  requestHandoff(): void {
    if (this.socket$) {
      this.socket$.next({ type: 'manual_handoff_request' });
    }
  }

  onEnter(event: Event): void {
    event.preventDefault();
    this.sendMessage();
  }

  submitFeedback(rating: string): void {
    if (!this.sessionId) return;
    this.http.post<any>(`${environment.apiUrl}/api/v1/sessions/${this.sessionId}/feedback`, {
      rating,
      comment: this.feedbackComment,
    }).subscribe({
      next: () => {
        this.feedbackGiven.set(true);
        this.showFeedbackComment.set(false);
      }
    });
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/login']);
  }

  formatDate(iso: string): string {
    try {
      const d = new Date(iso);
      const now = new Date();
      if (d.toDateString() === now.toDateString()) {
        return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
      }
      return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' });
    } catch { return ''; }
  }

  trackByIdx(index: number): number { return index; }

  private scrollToBottom(): void {
    try {
      this.messageContainer.nativeElement.scrollTop = this.messageContainer.nativeElement.scrollHeight;
    } catch { }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    this.stopPing();
    this.socket$?.complete();
  }
}
