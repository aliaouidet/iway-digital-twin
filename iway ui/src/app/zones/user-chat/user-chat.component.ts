import { Component, OnInit, OnDestroy, signal, ViewChild, ElementRef, AfterViewChecked, HostListener } from '@angular/core';
import { trigger, state, style, transition, animate } from '@angular/animations';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { retry, timer, Subject, takeUntil, Subscription, EMPTY, defer, throwError } from 'rxjs';
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
  /** Structured personal records (dossiers/bénéficiaires/réclamations…) —
   *  rendered as claim cards under the bubble. Live payload only, never persisted. */
  records?: any;
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
    <div class="h-screen flex transition-colors duration-300 bg-slate-50 dark:bg-[#020617]">

      <!-- Mobile Backdrop -->
      <div *ngIf="isSidebarOpen() && !isDesktopMode" 
           (click)="closeSidebar()"
           class="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-40 lg:hidden transition-opacity">
      </div>

      <aside class="w-72 flex flex-col border-r flex-shrink-0 absolute lg:relative z-50 h-full transition-transform duration-300 transform bg-white border-slate-200 dark:bg-[#0F172A] dark:border-slate-800"
        [class.translate-x-0]="isSidebarOpen() || isDesktopMode"
        [class.-translate-x-full]="!isSidebarOpen() && !isDesktopMode">
        <!-- Sidebar Header -->
        <div class="h-16 flex items-center justify-between px-4 border-b flex-shrink-0 border-slate-200 dark:border-slate-800">
          <div class="flex items-center gap-2">
            <div class="w-[80px] md:w-[110px] flex-shrink-0">
              <app-iway-logo width="100%"></app-iway-logo>
            </div>
          </div>
          <div class="flex items-center gap-1 z-10 relative">
            <button (click)="toggleTheme()" type="button" aria-label="Changer de thème" class="w-7 h-7 rounded-lg flex items-center justify-center transition-colors cursor-pointer hover:bg-slate-100 text-slate-400 dark:hover:bg-slate-800 dark:text-slate-500">
              <svg class="w-3.5 h-3.5 hidden dark:block" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"/></svg>
              <svg class="w-3.5 h-3.5 block dark:hidden" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"/></svg>
            </button>
            <button (click)="logout()" type="button" aria-label="Se déconnecter" class="w-7 h-7 rounded-lg flex items-center justify-center transition-colors cursor-pointer hidden md:flex hover:bg-slate-100 text-slate-400 hover:text-rose-500 dark:hover:bg-slate-800 dark:text-slate-500 dark:hover:text-rose-400">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9"/></svg>
            </button>
            <button (click)="closeSidebar()" type="button" aria-label="Fermer le menu" class="md:hidden w-7 h-7 rounded-lg flex items-center justify-center transition-colors cursor-pointer hover:bg-slate-100 text-slate-700 dark:hover:bg-slate-800 dark:text-slate-300">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
        </div>

        <!-- New Chat Button -->
        <div class="px-3 py-3">
          <button (click)="createNewChat()" class="w-full py-2.5 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center justify-center gap-2 bg-indigo-50 text-indigo-600 hover:bg-indigo-100 border border-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-400 dark:hover:bg-indigo-500/20 dark:border-indigo-500/20">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.5v15m7.5-7.5h-15"/></svg>
            Nouvelle conversation
          </button>
        </div>

        <!-- Chat List -->
        <div class="flex-1 overflow-y-auto px-3 space-y-2 py-2 custom-scrollbar">
          
          <!-- Active Chats Dropdown -->
          <div>
            <button (click)="isActiveChatsOpen.set(!isActiveChatsOpen())" class="w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-colors cursor-pointer hover:bg-slate-100/50 text-slate-700 dark:hover:bg-slate-800/50 dark:text-slate-300">
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
                  <span class="text-[10px] font-medium text-slate-400 dark:text-slate-500">{{formatDate(chat.created_at)}}</span>
                  <span *ngIf="chat.status === 'handoff_pending'" class="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400">Agent</span>
                </div>
                <p class="text-[11px] truncate text-slate-600 dark:text-slate-400">{{chat.last_message || 'Nouvelle conversation'}}</p>
                <span class="text-[10px] mt-0.5 block text-slate-400 dark:text-slate-600">{{chat.message_count}} messages</span>
              </button>
              <div *ngIf="activeThreads().length === 0" class="text-center py-4">
                <p class="text-[10px] text-slate-400 dark:text-slate-600">Aucune conversation active</p>
              </div>
            </div>
          </div>

          <!-- Resolved Chats Dropdown -->
          <div>
            <button (click)="isResolvedChatsOpen.set(!isResolvedChatsOpen())" class="w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-colors cursor-pointer hover:bg-slate-100/50 text-slate-700 dark:hover:bg-slate-800/50 dark:text-slate-300">
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
                  <span class="text-[10px] font-medium text-slate-400 dark:text-slate-500">{{formatDate(chat.created_at)}}</span>
                  <span class="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400">Résolu</span>
                </div>
                <p class="text-[11px] truncate text-slate-600 dark:text-slate-400">{{chat.last_message || 'Nouvelle conversation'}}</p>
                <span class="text-[10px] mt-0.5 block text-slate-400 dark:text-slate-600">{{chat.message_count}} messages</span>
              </button>
              <div *ngIf="resolvedThreads().length === 0" class="text-center py-4">
                <p class="text-[10px] text-slate-400 dark:text-slate-600">Aucune conversation résolue</p>
              </div>
            </div>
          </div>

        </div>
      </aside>

      <!-- Main Chat Panel -->
      <main class="flex-1 flex flex-col">
        <!-- Header -->
        <header class="h-16 flex items-center justify-between px-4 md:px-6 border-b flex-shrink-0 transition-colors relative z-30 bg-white/80 border-slate-200 backdrop-blur-md dark:bg-[#0F172A]/80 dark:border-slate-800">
          <div class="flex items-center gap-2 md:gap-3 min-w-0">
            <button (click)="toggleSidebar()" type="button" aria-label="Ouvrir le menu" class="lg:hidden p-1.5 -ml-1 rounded-lg transition-colors cursor-pointer flex-shrink-0 hover:bg-slate-100 text-slate-700 dark:hover:bg-slate-800 dark:text-slate-300">
                <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/></svg>
            </button>
            <div class="w-8 h-8 md:w-9 md:h-9 bg-gradient-to-br from-indigo-500 to-indigo-700 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-500/20 flex-shrink-0">
              <svg class="w-4 h-4 md:w-5 md:h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"/></svg>
            </div>
            <div class="truncate">
              <span class="text-sm md:text-base font-bold truncate text-slate-900 dark:text-white" style="font-family: 'Figtree', sans-serif;">I-Way Assistant</span>
              <div class="flex items-center gap-1.5">
                <span class="relative flex h-2 w-2">
                  <span *ngIf="connectionState() === 'connecting'" class="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-amber-400"></span>
                  <span class="relative inline-flex rounded-full h-2 w-2"
                    [ngClass]="{
                      'bg-emerald-500': connectionState() === 'online',
                      'bg-amber-500': connectionState() === 'connecting',
                      'bg-slate-400 dark:bg-slate-500': connectionState() === 'idle'
                    }"></span>
                </span>
                <span class="text-[10px] md:text-[10px] font-medium text-slate-400 dark:text-slate-500">{{connectionLabel()}}</span>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-1 md:gap-2 flex-shrink-0">
            <button *ngIf="!isHandoffActive() && sessionId" (click)="requestHandoff()"
              class="px-2.5 md:px-4 py-1.5 md:py-2 rounded-xl text-[10px] md:text-xs font-semibold transition-colors cursor-pointer flex items-center gap-1.5 bg-rose-50 text-rose-600 hover:bg-rose-100 border border-rose-200 dark:bg-rose-500/10 dark:text-rose-400 dark:hover:bg-rose-500/20 dark:border-rose-500/20">
              <svg class="w-3.5 h-3.5 hidden md:block" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/></svg>
              Parler à un agent
            </button>
            <button (click)="logout()" type="button" aria-label="Se déconnecter" class="lg:hidden w-8 h-8 rounded-lg flex items-center justify-center transition-colors cursor-pointer hover:bg-slate-100 text-slate-400 hover:text-rose-500 dark:hover:bg-slate-800 dark:text-slate-500 dark:hover:text-rose-400">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9"/></svg>
            </button>
          </div>
        </header>

        <!-- Handoff Banner (keep chatting) -->
        <div *ngIf="isHandoffPending()" class="px-6 py-3 flex items-center gap-3 border-b animate-fade-in bg-amber-50 border-amber-200 dark:bg-amber-500/10 dark:border-amber-500/20">
          <div class="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 bg-amber-100 dark:bg-amber-500/20">
            <svg class="w-4 h-4 animate-pulse text-amber-600 dark:text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          </div>
          <div class="min-w-0">
            <p class="text-xs font-semibold text-amber-800 dark:text-amber-300 flex items-center gap-2">
              Un agent va vous rejoindre bientôt
              <span *ngIf="handoffPosition()" class="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300">
                Position {{handoffPosition()}}<span *ngIf="handoffWaitMin()"> · ≈ {{handoffWaitMin()}} min</span>
              </span>
            </p>
            <p class="text-[10px] text-amber-600 dark:text-amber-400/70">
              Vous pouvez continuer à poser des questions en attendant.
            </p>
          </div>
        </div>

        <!-- Agent Joined Banner -->
        <div *ngIf="agentName()" class="px-6 py-3 flex items-center gap-3 border-b animate-fade-in bg-emerald-50 border-emerald-200 dark:bg-emerald-500/10 dark:border-emerald-500/20">
          <div class="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 bg-emerald-100 dark:bg-emerald-500/20">
            <svg class="w-4 h-4 text-emerald-600 dark:text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          </div>
          <div>
            <p class="text-xs font-semibold text-emerald-800 dark:text-emerald-300">
              {{agentName()}} a rejoint la conversation
            </p>
            <p class="text-[10px] text-emerald-600 dark:text-emerald-400/70">
              Vous discutez maintenant avec un agent. Il a lu le résumé de votre conversation.
            </p>
          </div>
        </div>

        <!-- Messages -->
        <div #messageContainer class="flex-1 overflow-y-auto px-4 py-6 space-y-4 custom-scrollbar">
          <!-- Welcome (no active session yet) -->
          <div *ngIf="messages().length === 0" class="flex flex-col items-center justify-center h-full text-center px-4">
            <div class="w-16 h-16 rounded-2xl flex items-center justify-center mb-5 bg-indigo-50 dark:bg-indigo-500/10">
              <svg class="w-8 h-8 text-indigo-500 dark:text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8.625 9.75a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 01.778-.332 48.294 48.294 0 005.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z"/></svg>
            </div>
            <h2 class="text-xl font-bold mb-2 text-slate-900 dark:text-white" style="font-family: 'Figtree', sans-serif;">Bienvenue sur I-Way Support</h2>
            <p class="text-sm max-w-md text-slate-500 dark:text-slate-500">
              Posez une question générale, consultez votre dossier personnel, ou demandez un agent à tout moment.
            </p>

            <!-- Questions générales -->
            <div class="mt-7 w-full max-w-lg">
              <p class="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-600 mb-2">Questions générales</p>
              <div class="flex flex-wrap gap-2 justify-center">
                <button *ngFor="let q of quickQuestions" (click)="sendQuickQuestion(q)" type="button"
                  class="px-3.5 py-2 rounded-xl text-xs font-medium transition-colors cursor-pointer bg-white hover:bg-slate-50 text-slate-600 border border-slate-200 shadow-sm dark:bg-slate-800 dark:hover:bg-slate-700 dark:text-slate-400 dark:border-slate-700">
                  {{q}}
                </button>
              </div>
            </div>

            <!-- Mon dossier (personal data) -->
            <div class="mt-5 w-full max-w-lg">
              <p class="text-[10px] font-semibold uppercase tracking-wider text-indigo-400 dark:text-indigo-500 mb-2">Mon dossier</p>
              <div class="flex flex-wrap gap-2 justify-center">
                <button *ngFor="let q of personalQuestions" (click)="sendQuickQuestion(q)" type="button"
                  class="px-3.5 py-2 rounded-xl text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 border border-indigo-200 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 dark:text-indigo-400 dark:border-indigo-500/20">
                  <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/></svg>
                  {{q}}
                </button>
              </div>
            </div>
          </div>

          <!-- Message Bubbles -->
          <div *ngFor="let msg of messages(); let i = index; trackBy: trackByIdx">
            <!-- Day separator -->
            <div *ngIf="isNewDay(i)" class="flex justify-center my-3">
              <span class="px-3 py-1 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-400 dark:bg-slate-800/60 dark:text-slate-500">{{dayLabel(msg.timestamp)}}</span>
            </div>
            <!-- System Message -->
            <div *ngIf="msg.role === 'system'" class="flex justify-center">
              <div class="px-4 py-2 rounded-full text-xs font-medium bg-slate-100 text-slate-500 dark:bg-slate-800/50 dark:text-slate-500" [innerHTML]="formatMessage(msg.content)">
              </div>
            </div>
            <!-- User Message -->
            <div *ngIf="msg.role === 'user'" class="flex flex-col items-end">
              <div class="max-w-[75%] px-4 py-3 rounded-2xl rounded-br-md text-sm bg-indigo-600 text-white" [innerHTML]="formatMessage(msg.content)">
              </div>
              <span *ngIf="msg.timestamp" class="text-[10px] text-slate-400 dark:text-slate-600 mt-1 mr-1">{{formatTime(msg.timestamp)}}</span>
            </div>
            <!-- AI / Agent Message -->
            <div *ngIf="msg.role === 'assistant' || msg.role === 'agent'" class="flex justify-start gap-2.5">
              <div class="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-1"
                [class.invisible]="isGroupedWith(i)"
                [ngClass]="{
                  'bg-amber-100 dark:bg-amber-500/20': msg.role === 'agent',
                  'bg-orange-50 dark:bg-orange-500/10': msg.role !== 'agent' && msg.is_handoff_ai,
                  'bg-indigo-50 dark:bg-indigo-500/10': msg.role !== 'agent' && !msg.is_handoff_ai
                }">
                <svg *ngIf="msg.role === 'assistant' && !msg.is_handoff_ai" class="w-3.5 h-3.5 text-indigo-500 dark:text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/></svg>
                <svg *ngIf="msg.is_handoff_ai" class="w-3.5 h-3.5 text-orange-500 dark:text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                <svg *ngIf="msg.role === 'agent'" class="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/></svg>
              </div>
              <div class="flex-1 min-w-0">
                <!-- Sender label (first message of a group) -->
                <div *ngIf="!isGroupedWith(i)" class="text-[10px] font-semibold text-slate-400 dark:text-slate-500 mb-0.5 ml-1">
                  {{msg.role === 'agent' ? (agentName() || 'Agent I-Way') : 'Assistant I-Way'}}
                </div>
                <!-- Handoff AI badge -->
                <div *ngIf="msg.is_handoff_ai" class="mb-1">
                  <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-orange-50 text-orange-600 border border-orange-200 dark:bg-orange-500/10 dark:text-orange-400 dark:border-orange-500/20">
                    ⏳ En attendant l'agent
                  </span>
                </div>
                <div class="group relative max-w-[75%] w-fit">
                  <div class="px-4 py-3 rounded-2xl rounded-bl-md text-sm shadow-sm border"
                    [ngClass]="{
                      'bg-orange-50 border-orange-200 text-orange-900 dark:bg-orange-500/5 dark:border-orange-500/20 dark:text-orange-200': msg.is_handoff_ai,
                      'bg-white border-slate-200 text-slate-700 dark:bg-[#0F172A] dark:border-slate-800 dark:text-slate-300': !msg.is_handoff_ai
                    }">
                    <span [innerHTML]="formatMessage(msg.content)"></span><span *ngIf="msg.isStreaming" class="inline-block w-1.5 h-4 ml-0.5 rounded-sm animate-pulse bg-indigo-500 dark:bg-indigo-400"></span>
                  </div>
                  <!-- Copy (hover) -->
                  <button *ngIf="msg.role === 'assistant' && !msg.isStreaming" (click)="copyMessage(msg.content)" type="button" aria-label="Copier la réponse"
                    class="absolute -right-2 -top-2 w-6 h-6 rounded-lg hidden group-hover:flex items-center justify-center cursor-pointer shadow-sm bg-white border border-slate-200 text-slate-400 hover:text-indigo-500 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-500 dark:hover:text-indigo-400">
                    <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
                  </button>
                </div>

                <!-- Claim cards (structured records — live payload only) -->
                <div *ngIf="msg.records as r" class="mt-2 max-w-md space-y-2">
                  <!-- Honest degradation -->
                  <div *ngIf="r.service_indisponible" class="rounded-xl border px-3 py-2.5 text-xs flex items-start gap-2 bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-500/10 dark:border-amber-500/20 dark:text-amber-300">
                    <svg class="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>
                    <span>Service I-Way temporairement indisponible — vos données n'ont pas pu être vérifiées.</span>
                  </div>

                  <!-- Dossiers de remboursement -->
                  <div *ngFor="let d of r.dossiers" class="rounded-xl border p-3 bg-white border-slate-200 shadow-sm dark:bg-slate-800/60 dark:border-slate-700">
                    <div class="flex items-center justify-between gap-2">
                      <span class="text-xs font-bold font-mono text-slate-800 dark:text-white truncate">{{d.id || d.num_dossier || 'Dossier'}}</span>
                      <span class="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase flex-shrink-0" [class]="recordStatusClass(d.status)">{{recordStatusLabel(d.status)}}</span>
                    </div>
                    <div class="flex items-center justify-between gap-2 mt-1.5 text-xs">
                      <span class="text-slate-500 dark:text-slate-400 capitalize truncate">{{d.type || 'Soins'}}<ng-container *ngIf="d.date_soins"> · {{d.date_soins}}</ng-container></span>
                      <span class="font-semibold text-slate-700 dark:text-slate-200 flex-shrink-0">
                        <ng-container *ngIf="d.montant != null">{{d.montant}} TND</ng-container>
                        <span *ngIf="d.montant_rembourse != null" class="text-emerald-600 dark:text-emerald-400"> → {{d.montant_rembourse}} TND</span>
                      </span>
                    </div>
                  </div>

                  <!-- Plafond annuel -->
                  <div *ngIf="r.plafond_annuel" class="rounded-xl border p-3 bg-white border-slate-200 shadow-sm dark:bg-slate-800/60 dark:border-slate-700">
                    <div class="flex items-center justify-between text-[11px] mb-1.5">
                      <span class="text-slate-500 dark:text-slate-400">Plafond annuel consommé</span>
                      <span class="font-bold text-slate-700 dark:text-slate-200">{{r.total_rembourse_2026 || 0}} / {{r.plafond_annuel}} TND</span>
                    </div>
                    <div class="h-1.5 rounded-full bg-slate-100 dark:bg-slate-700 overflow-hidden">
                      <div class="h-full rounded-full transition-all bg-gradient-to-r from-indigo-500 to-emerald-500" [style.width.%]="plafondPct(r)"></div>
                    </div>
                  </div>

                  <!-- Bénéficiaires -->
                  <div *ngIf="r.beneficiaires?.length" class="rounded-xl border p-3 bg-white border-slate-200 shadow-sm dark:bg-slate-800/60 dark:border-slate-700">
                    <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-1.5">Bénéficiaires ({{r.beneficiaires.length}})</div>
                    <div *ngFor="let b of r.beneficiaires" class="flex items-center justify-between gap-2 text-xs py-1 border-b last:border-0 border-slate-100 dark:border-slate-700/50">
                      <span class="flex items-center gap-1.5 text-slate-700 dark:text-slate-200 truncate">
                        <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" [class]="b.couverture_active === false ? 'bg-rose-500' : 'bg-emerald-500'"></span>
                        {{b.nom_complet || b.nom}}
                      </span>
                      <span *ngIf="b.lien" class="px-1.5 py-0.5 rounded text-[10px] capitalize flex-shrink-0 bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">{{b.lien}}</span>
                    </div>
                  </div>

                  <!-- Réclamations -->
                  <div *ngIf="r.reclamations?.length" class="rounded-xl border p-3 bg-white border-slate-200 shadow-sm dark:bg-slate-800/60 dark:border-slate-700">
                    <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-1.5">Réclamations ({{r.reclamations.length}})</div>
                    <div *ngFor="let rec of r.reclamations" class="py-1.5 border-b last:border-0 border-slate-100 dark:border-slate-700/50">
                      <div class="flex items-center justify-between gap-2 text-xs">
                        <span class="font-mono font-bold text-slate-800 dark:text-white truncate">{{rec.numero}}</span>
                        <span class="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase flex-shrink-0" [class]="reclStatusClass(rec.statut)">{{rec.statut || 'En cours'}}</span>
                      </div>
                      <div class="text-[11px] text-slate-500 dark:text-slate-400 truncate mt-0.5">{{rec.objet}}<ng-container *ngIf="rec.date"> · {{rec.date}}</ng-container></div>
                      <div *ngIf="rec.reponse" class="text-[11px] text-emerald-600 dark:text-emerald-400 mt-0.5 truncate">↳ {{rec.reponse}}</div>
                    </div>
                  </div>

                  <!-- Détail d'un dossier -->
                  <div *ngIf="r.dossier_detail as dd" class="rounded-xl border p-3 bg-white border-slate-200 shadow-sm dark:bg-slate-800/60 dark:border-slate-700">
                    <div class="flex items-center justify-between gap-2 mb-1.5">
                      <span class="text-xs font-bold font-mono text-slate-800 dark:text-white">{{dd.num_dossier || 'Détail du dossier'}}</span>
                      <span *ngIf="dd.statut" class="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase" [class]="recordStatusClass(dd.statut)">{{recordStatusLabel(dd.statut)}}</span>
                    </div>
                    <div class="space-y-1 text-xs text-slate-600 dark:text-slate-300">
                      <div *ngIf="dd.date" class="flex justify-between"><span class="text-slate-400 dark:text-slate-500">Date</span><span>{{dd.date}}</span></div>
                      <div *ngIf="dd.beneficiaire" class="flex justify-between"><span class="text-slate-400 dark:text-slate-500">Bénéficiaire</span><span>{{dd.beneficiaire}}</span></div>
                      <div *ngIf="dd.actes?.length" class="flex justify-between gap-3"><span class="text-slate-400 dark:text-slate-500 flex-shrink-0">Actes</span><span class="text-right">{{dd.actes.join(', ')}}</span></div>
                      <div *ngIf="dd.montant_total != null" class="flex justify-between"><span class="text-slate-400 dark:text-slate-500">Montant</span><span class="font-semibold">{{dd.montant_total}} TND</span></div>
                      <div *ngIf="dd.montant_rembourse != null" class="flex justify-between"><span class="text-slate-400 dark:text-slate-500">Remboursé</span><span class="font-semibold text-emerald-600 dark:text-emerald-400">{{dd.montant_rembourse}} TND<ng-container *ngIf="dd.taux_remboursement"> ({{dd.taux_remboursement}}%)</ng-container></span></div>
                    </div>
                  </div>

                  <!-- Contrat -->
                  <div *ngIf="r.contrat as c" class="rounded-xl border p-3 bg-white border-slate-200 shadow-sm dark:bg-slate-800/60 dark:border-slate-700">
                    <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-1.5">Contrat</div>
                    <div class="space-y-1 text-xs text-slate-600 dark:text-slate-300">
                      <div *ngIf="c.num_police" class="flex justify-between"><span class="text-slate-400 dark:text-slate-500">Police</span><span class="font-mono">{{c.num_police}}</span></div>
                      <div *ngIf="c.titulaire" class="flex justify-between"><span class="text-slate-400 dark:text-slate-500">Titulaire</span><span>{{c.titulaire}}</span></div>
                      <div *ngIf="c.produit" class="flex justify-between"><span class="text-slate-400 dark:text-slate-500">Produit</span><span>{{c.produit}}</span></div>
                      <div *ngIf="c.statut" class="flex justify-between"><span class="text-slate-400 dark:text-slate-500">Statut</span><span>{{c.statut}}</span></div>
                    </div>
                  </div>
                </div>

                <span *ngIf="msg.timestamp && !msg.isStreaming" class="block text-[10px] text-slate-400 dark:text-slate-600 mt-1 ml-1">{{formatTime(msg.timestamp)}}</span>
              </div>
            </div>
          </div>

          <!-- Thinking indicator -->
          <div *ngIf="isThinking()" class="flex justify-start gap-2.5">
            <div class="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 bg-indigo-50 dark:bg-indigo-500/10">
              <svg class="w-3.5 h-3.5 text-indigo-500 dark:text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/></svg>
            </div>
            <div class="px-4 py-3 rounded-2xl rounded-bl-md bg-white border border-slate-200 shadow-sm dark:bg-[#0F172A] dark:border-slate-800">
              <div class="flex items-center gap-3">
                <div class="flex gap-1">
                  <span class="w-2 h-2 rounded-full animate-bounce bg-indigo-500 dark:bg-indigo-400" style="animation-delay: 0ms"></span>
                  <span class="w-2 h-2 rounded-full animate-bounce bg-indigo-500 dark:bg-indigo-400" style="animation-delay: 150ms"></span>
                  <span class="w-2 h-2 rounded-full animate-bounce bg-indigo-500 dark:bg-indigo-400" style="animation-delay: 300ms"></span>
                </div>
                <span *ngIf="thinkingStatus()" class="text-[10px] font-medium animate-pulse text-indigo-500/70 dark:text-indigo-400/70">
                  {{thinkingStatus()}}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- CSAT Feedback Widget -->
        <div *ngIf="isSessionResolved() && !feedbackGiven()" class="px-4 py-4 border-t flex-shrink-0 transition-all bg-indigo-50 border-indigo-200 dark:bg-indigo-500/5 dark:border-indigo-500/20">
          <div class="max-w-3xl mx-auto">
            <div *ngIf="!showFeedbackComment()" class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <svg class="w-4 h-4 text-indigo-500 dark:text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z"/></svg>
                <span class="text-xs font-semibold text-indigo-700 dark:text-indigo-300">Cette conversation vous a-t-elle été utile ?</span>
              </div>
              <div class="flex items-center gap-2">
                <button (click)="submitFeedback('positive')" class="px-4 py-2 rounded-xl text-xs font-semibold cursor-pointer transition-all flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 bg-emerald-50 text-emerald-600 hover:bg-emerald-100 border border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:hover:bg-emerald-500/20 dark:border-emerald-500/20">
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6.633 10.5c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 012.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 00.322-1.672V3a.75.75 0 01.75-.75A2.25 2.25 0 0116.5 4.5c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 01-2.649 7.521c-.388.482-.987.729-1.605.729H13.48c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 00-1.423-.23H5.904M14.25 9h2.25M5.904 18.75c.083.205.173.405.27.602.197.4-.078.898-.523.898h-.908c-.889 0-1.713-.518-1.972-1.368a12 12 0 01-.521-3.507c0-1.553.295-3.036.831-4.398C3.387 10.203 4.167 9.75 5 9.75h1.053c.472 0 .745.556.5.96a8.958 8.958 0 00-1.302 4.665c0 1.194.232 2.333.654 3.375z"/></svg>
                  Oui
                </button>
                <button (click)="showFeedbackComment.set(true); feedbackRating = 'negative'" class="px-4 py-2 rounded-xl text-xs font-semibold cursor-pointer transition-all flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-rose-500/50 bg-rose-50 text-rose-600 hover:bg-rose-100 border border-rose-200 dark:bg-rose-500/10 dark:text-rose-400 dark:hover:bg-rose-500/20 dark:border-rose-500/20">
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7.5 15h2.25m8.024-9.75c.011.05.028.1.052.148.591 1.2.924 2.55.924 3.977a8.96 8.96 0 01-.999 4.125m.023-8.25c-.076-.365.183-.75.575-.75h.908c.889 0 1.713.518 1.972 1.368.339 1.11.521 2.287.521 3.507 0 1.553-.295 3.036-.831 4.398-.306.774-1.086 1.227-1.918 1.227h-1.053c-.472 0-.745-.556-.5-.96a8.95 8.95 0 00.303-.54m.023-8.25H16.48a4.5 4.5 0 01-1.423-.23l-3.114-1.04a4.5 4.5 0 00-1.423-.23H6.504c-.618 0-1.217.247-1.605.729A11.95 11.95 0 002.25 12c0 .434.023.863.068 1.285C2.427 14.306 3.346 15 4.372 15h3.126c.618 0 .991.724.725 1.282A7.471 7.471 0 007.5 19.5a2.25 2.25 0 002.25 2.25.75.75 0 00.75-.75v-.633c0-.573.11-1.14.322-1.672.304-.76.93-1.33 1.653-1.715a9.04 9.04 0 002.86-2.4c.498-.634 1.226-1.08 2.032-1.08h.384"/></svg>
                  Non
                </button>
              </div>
            </div>
            <!-- Comment input for negative feedback -->
            <div *ngIf="showFeedbackComment()" class="space-y-3">
              <p class="text-xs font-semibold text-rose-700 dark:text-rose-300">Qu'est-ce qui pourrait être amélioré ?</p>
              <textarea [(ngModel)]="feedbackComment" rows="2" placeholder="Votre commentaire (optionnel)..."
                class="w-full px-3 py-2 rounded-lg text-xs transition-all focus:outline-none focus:ring-1 focus:ring-indigo-500/50 resize-none bg-white border border-slate-200 text-slate-900 placeholder-slate-400 dark:bg-slate-800/50 dark:border-slate-700 dark:text-white dark:placeholder-slate-500"></textarea>
              <div class="flex gap-2">
                <button (click)="submitFeedback('negative')" class="px-4 py-2 rounded-lg text-[10px] font-semibold cursor-pointer transition-colors bg-rose-600 hover:bg-rose-500 text-white focus:outline-none focus:ring-2 focus:ring-rose-500/50">Envoyer</button>
                <button (click)="showFeedbackComment.set(false)" class="px-4 py-2 rounded-lg text-[10px] font-semibold cursor-pointer transition-colors bg-white text-slate-600 border border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-transparent">Annuler</button>
              </div>
            </div>
            <!-- Thank you message -->
          </div>
        </div>

        <!-- Thank you after feedback -->
        <div *ngIf="feedbackGiven()" class="px-4 py-3 border-t flex-shrink-0 text-center bg-emerald-50 border-emerald-200 dark:bg-emerald-500/5 dark:border-emerald-500/20">
          <p class="text-xs font-semibold text-emerald-700 dark:text-emerald-400">Merci pour votre retour !</p>
        </div>

        <!-- Input -->
        <div *ngIf="!isSessionResolved()" class="px-4 py-4 border-t flex-shrink-0 transition-colors bg-white border-slate-200 dark:bg-[#0F172A]/60 dark:border-slate-800">
          <form (ngSubmit)="sendMessage()" class="max-w-3xl mx-auto">
            <div class="flex items-end gap-3">
              <div class="flex-1 relative">
                <textarea #msgInput [(ngModel)]="newMessage" name="msg" rows="1"
                  placeholder="Écrivez votre message..."
                  class="w-full px-4 py-3 rounded-xl text-sm transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500/50 resize-none bg-slate-50 border border-slate-200 text-slate-900 placeholder-slate-400 dark:bg-slate-800/50 dark:border-slate-700 dark:text-white dark:placeholder-slate-500 max-h-40 overflow-y-auto"
                  (input)="autoGrow($event)"
                  (keydown.enter)="$any($event).shiftKey ? null : onEnter($event)"></textarea>
              </div>
              <button type="submit" [disabled]="!newMessage.trim()" aria-label="Envoyer le message"
                class="w-11 h-11 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 rounded-xl flex items-center justify-center text-white transition-all cursor-pointer disabled:cursor-not-allowed flex-shrink-0">
                <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"/></svg>
              </button>
            </div>
            <p class="text-[10px] text-slate-400 dark:text-slate-600 mt-1.5 ml-1">
              <kbd class="font-sans">Entrée</kbd> pour envoyer · <kbd class="font-sans">Maj+Entrée</kbd> pour un saut de ligne
            </p>
          </form>
        </div>
      </main>
    </div>
  `
})
export class UserChatComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('messageContainer') private messageContainer!: ElementRef;
  @ViewChild('msgInput') private msgInput?: ElementRef<HTMLTextAreaElement>;

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
  handoffPosition = signal<number | null>(null);
  handoffWaitMin = signal<number | null>(null);
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
  private pendingMessages: string[] = [];  // Messages waiting for the WS to (re)connect
  private authExpired = false;             // Set when the server closes with 4001/4003

  // Generic FAQ — answered from the knowledge base.
  quickQuestions = [
    'Plafond soins dentaires ?',
    'Délai de remboursement ?',
    'Prime de naissance ?',
    'Numéro urgences ?',
  ];

  // Personal-record prompts — surface the highest-value feature (consulting
  // your own data) that a new user otherwise never discovers. Wording matches
  // the personal_lookup router exemplars (réclamation STATUS, not filing).
  personalQuestions = [
    'Mes remboursements',
    'Mes bénéficiaires',
    'Où en est ma réclamation ?',
  ];

  constructor(
    private authService: AuthService,
    private themeService: ThemeService,
    private http: HttpClient,
    private router: Router,
    private toastService: ToastService
  ) { }

  toggleTheme = () => this.themeService.toggleTheme();

  /** 3-state connection status for the header. Without it, the idle welcome
   *  screen (no session, no socket) shows a perpetual "Connexion…" that reads
   *  as broken. */
  connectionState = (): 'idle' | 'online' | 'connecting' => {
    if (!this.sessionId) return 'idle';
    return this.isConnected() ? 'online' : 'connecting';
  };

  connectionLabel = (): string => {
    switch (this.connectionState()) {
      case 'online': return 'En ligne';
      case 'connecting': return 'Connexion...';
      default: return 'Prêt';
    }
  };

  formatMessage(text: string): string {
    if (!text) return '';
    // SECURITY: escape HTML entities BEFORE the markdown transforms — message
    // content (user, agent, AI) is untrusted and rendered via [innerHTML].
    // Angular's sanitizer is a second line of defense, not the only one.
    let formatted = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    // Format bold: **text**
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Format italic: *text* (only if not already bold)
    formatted = formatted.replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
    // Format lists: * item
    formatted = formatted.replace(/^\s*\*\s+(.*)$/gm, '• $1');
    // Format newlines
    formatted = formatted.replace(/\n/g, '<br>');
    return formatted;
  }

  ngOnInit(): void {
    this.checkScreenSize();
    // resumeLastActiveChat() also populates chatThreads — no separate
    // loadChatThreads() call (it would duplicate the same GET).
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
    this.handoffPosition.set(null);
    this.handoffWaitMin.set(null);
    this.agentName.set('');
    this.isSessionResolved.set(false);
    this.streamingContent = '';
    this.sessionId = '';

    // Don't create a backend session yet!
    // It will be created lazily when the user sends their first message.
    // This prevents empty ghost sessions on every button click.
  }

  switchChat(chat: ChatThread): void {
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
    if (active) {
      return 'bg-indigo-50 border border-indigo-200 dark:bg-indigo-500/10 dark:border-indigo-500/30';
    }
    return 'hover:bg-slate-50 border border-transparent dark:hover:bg-slate-800/50';
  }

  // ─── WebSocket ───

  /** Build the socket fresh — called on every connection attempt so retries
   *  pick up a re-issued token (e.g. after re-login in another tab). */
  private createSocket(): WebSocketSubject<any> {
    const token = this.authService.getToken() || '';
    // Token travels in the FIRST frame, not the URL — query strings leak into
    // proxy logs and browser history.
    const wsUrl = `${environment.wsUrl.replace('/events', '')}/chat/${this.sessionId}`;

    const socket: WebSocketSubject<any> = webSocket<any>({
      url: wsUrl,
      deserializer: (e) => JSON.parse(e.data),
      openObserver: {
        next: () => {
          // Auth handshake first, then announce ourselves.
          socket.next({ type: 'auth', token });
          socket.next({ type: 'user_connect' });
          // Start heartbeat
          this.startPing();
        }
      },
      closeObserver: {
        next: (event: CloseEvent) => {
          console.log('[UserChat WS] Connection closed', event.code);
          this.isConnected.set(false);
          this.stopPing();
          // 4001/4003 = backend rejected the token — retrying is pointless
          if (event.code === 4001 || event.code === 4003) {
            this.authExpired = true;
          }
        }
      }
    });
    this.socket$ = socket;
    return socket;
  }

  private connectWebSocket(): void {
    // Clean up existing connection
    this.stopPing();
    if (this.socket$ && !this.socket$.closed) {
      this.socket$.complete();
    }
    this.authExpired = false;

    defer(() => this.createSocket()).pipe(
      retry({
        count: 5,
        delay: (error, retryCount) => {
          if (this.authExpired) {
            return throwError(() => new Error('auth_expired'));
          }
          const delayMs = Math.min(2000 * Math.pow(2, retryCount - 1), 30000);
          console.log(`[UserChat WS] Reconnecting in ${delayMs}ms (attempt ${retryCount})...`);
          return timer(delayMs);
        },
        resetOnSuccess: true,
      }),
      catchError(err => {
        console.error('[UserChat WS] Fatal error:', err);
        this.isConnected.set(false);
        this.socket$ = null;   // allow a later sendMessage() to reconnect
        if (this.authExpired) {
          this.toastService.show('Session expirée. Veuillez vous reconnecter.', 'error');
          this.authService.logout();
          this.router.navigate(['/login']);
        } else {
          this.toastService.show('Connexion perdue. Votre message sera envoyé à la reconnexion.', 'error');
        }
        return EMPTY;
      }),
      takeUntil(this.destroy$)
    ).subscribe({
      next: (msg) => this.handleWsMessage(msg),
      error: (err) => { console.error('[UserChat WS] Stream error:', err); this.isConnected.set(false); },
      complete: () => this.isConnected.set(false),
    });
  }

  /** Send everything queued while we were disconnected (after backend confirms the bind). */
  private flushPendingMessages(): void {
    if (!this.pendingMessages.length) return;
    for (const content of this.pendingMessages) {
      this.socket$?.next({ type: 'user_message', content });
    }
    this.pendingMessages = [];
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
        this.isConnected.set(true);
        this.flushPendingMessages();
        break;
      case 'history':
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
        this.isThinking.set(false);
        this.thinkingStatus.set('');
        const updated = this.messages();
        const lastMsg = updated[updated.length - 1];
        if (lastMsg?.isStreaming) {
          // Finalize the streaming bubble. ai_done.text is the AUTHORITATIVE
          // final answer (PII-restored, compliance-redacted server-side) — it
          // must REPLACE the raw streamed content, which may contain [PII_n]
          // placeholders or internal artifacts when the backend streamed the
          // structured-output fallback path.
          this.messages.set([...updated.slice(0, -1), {
            ...lastMsg,
            content: msg.text || lastMsg.content,
            isStreaming: false,
            is_handoff_ai: msg.is_handoff_ai || false,
            confidence: msg.confidence,
            records: msg.records || undefined,
            timestamp: new Date().toISOString(),
          }]);
        } else if (msg.text) {
          // No streaming bubble (the normal graph path streams no tokens):
          // append the full response from ai_done.
          this.messages.update(msgs => [...msgs, {
            role: 'assistant',
            content: msg.text,
            is_handoff_ai: msg.is_handoff_ai || false,
            confidence: msg.confidence,
            records: msg.records || undefined,
            timestamp: new Date().toISOString(),
          }]);
        }
        this.streamingContent = '';
        this.loadChatThreads(); // Update sidebar
        break;
      case 'handoff_started':
        const alreadyPending = this.isHandoffPending();
        this.isHandoffActive.set(true);
        this.isHandoffPending.set(true);
        this.isThinking.set(false);
        this.handoffPosition.set(msg.queue_position ?? null);
        this.handoffWaitMin.set(msg.estimated_wait_min ?? null);
        // Only announce once — re-escalation while already pending must not spam a
        // second toast + system bubble (the banner already reflects the new position).
        if (!alreadyPending) {
          this.toastService.show('Votre demande a été transmise à un conseiller', 'info');
          // DON'T disable input — user can keep chatting!
          this.messages.update(m => [...m, {
            role: 'system',
            content: msg.keep_chatting
              ? 'Un agent va vous rejoindre bientôt. Vous pouvez continuer à poser des questions.'
              : (msg.reason || 'Transfert vers un spécialiste...')
          }]);
        }
        this.loadChatThreads();
        break;
      case 'agent_joined':
        this.agentName.set(msg.agent_name || 'Agent');
        this.isHandoffPending.set(false);
        this.handoffPosition.set(null);
        this.handoffWaitMin.set(null);
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
    this.resetInputHeight();

    // Lazy session creation: if no session exists yet, create one first
    if (!this.sessionId) {
      this.messages.update(m => [...m, { role: 'user', content, timestamp: new Date().toISOString() }]);
      this.isThinking.set(true);
      this.thinkingStatus.set('Création de la session...');
      this.http.post<{ session_id: string }>(`${environment.apiUrl}/api/v1/sessions/create`, {}).subscribe({
        next: (res) => {
          this.sessionId = res.session_id;
          this.pendingMessages.push(content);  // Queue the message for after WS connects
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
    this.messages.update(m => [...m, { role: 'user', content, timestamp: new Date().toISOString() }]);
    if (this.socket$ && this.isConnected()) {
      this.socket$.next({ type: 'user_message', content });
    } else {
      // Socket dead or still connecting — never drop silently: queue the
      // message (flushed on 'connected') and re-establish if needed.
      this.pendingMessages.push(content);
      if (!this.socket$) {
        this.connectWebSocket();
      }
    }
  }

  sendQuickQuestion(q: string): void {
    this.newMessage = q;
    this.sendMessage();
  }

  // ─── Message presentation helpers ───

  formatTime(ts?: string): string {
    if (!ts) return '';
    try {
      return new Date(ts).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    } catch { return ''; }
  }

  /** Consecutive assistant/agent messages share one avatar + sender label. */
  isGroupedWith(i: number): boolean {
    const msgs = this.messages();
    const prev = msgs[i - 1];
    const cur = msgs[i];
    return !!prev && !!cur && prev.role === cur.role
      && (cur.role === 'assistant' || cur.role === 'agent');
  }

  isNewDay(i: number): boolean {
    const msgs = this.messages();
    const cur = msgs[i];
    if (!cur?.timestamp) return false;
    const prevTs = msgs.slice(0, i).reverse().find(m => m.timestamp)?.timestamp;
    if (!prevTs) return true;
    return new Date(cur.timestamp).toDateString() !== new Date(prevTs).toDateString();
  }

  dayLabel(ts?: string): string {
    if (!ts) return '';
    const d = new Date(ts);
    if (d.toDateString() === new Date().toDateString()) return "Aujourd'hui";
    return d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
  }

  copyMessage(content: string): void {
    navigator.clipboard?.writeText(content).then(
      () => this.toastService.show('Réponse copiée', 'success'),
      () => this.toastService.show('Copie impossible', 'error'),
    );
  }

  // ─── Claim-card helpers ───

  recordStatusClass(status?: string): string {
    const s = (status || '').toLowerCase();
    if (s.includes('rembours') || s.includes('regl')) return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400';
    if (s.includes('rejet') || s.includes('refus')) return 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400';
    return 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400';
  }

  recordStatusLabel(status?: string): string {
    if (!status) return 'En cours';
    if (status === 'rembourse') return 'Remboursé';
    if (status === 'en_cours') return 'En cours';
    return status;
  }

  reclStatusClass(statut?: string): string {
    const s = (statut || '').toLowerCase();
    if (s.includes('clôtur') || s.includes('clotur') || s.includes('trait')) return 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400';
    return 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400';
  }

  plafondPct(r: any): number {
    const plafond = Number(r?.plafond_annuel) || 0;
    const used = Number(r?.total_rembourse_2026) || 0;
    if (!plafond) return 0;
    return Math.max(0, Math.min(100, Math.round((used / plafond) * 100)));
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

  /** Grow the input with its content, capped (max-h-40 in the template). */
  autoGrow(event: Event): void {
    const el = event.target as HTMLTextAreaElement;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }

  /** Collapse the textarea back to one row after a message is sent. */
  private resetInputHeight(): void {
    const el = this.msgInput?.nativeElement;
    if (el) el.style.height = 'auto';
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
