import { Component, OnInit, OnDestroy, signal, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { environment } from '../../../environments/environment';
import { AuthService } from '../../core/services/auth.service';
import { ThemeService } from '../../core/services/theme.service';

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
  imports: [CommonModule, FormsModule],
  template: `
    <div class="h-screen flex transition-colors duration-300"
      [class]="isDark() ? 'bg-[#020617]' : 'bg-slate-50'">

      <!-- Left Sidebar: Chat History -->
      <aside class="w-72 flex flex-col border-r flex-shrink-0 transition-colors"
        [class]="isDark() ? 'bg-[#0F172A] border-slate-800' : 'bg-white border-slate-200'">
        <!-- Sidebar Header -->
        <div class="h-16 flex items-center justify-between px-4 border-b flex-shrink-0"
          [class]="isDark() ? 'border-slate-800' : 'border-slate-200'">
          <div class="flex items-center gap-2">
            <div class="w-8 h-8 bg-gradient-to-br from-indigo-500 to-indigo-700 rounded-lg flex items-center justify-center">
              <svg class="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.625 9.75a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 01.778-.332 48.294 48.294 0 005.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z"/></svg>
            </div>
            <span class="text-sm font-bold" style="font-family: 'Figtree', sans-serif;"
              [class]="isDark() ? 'text-white' : 'text-slate-900'">Mes Chats</span>
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
        <div class="flex-1 overflow-y-auto px-3 space-y-1 custom-scrollbar">
          <button *ngFor="let chat of chatThreads()" (click)="switchChat(chat)"
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
          <div *ngIf="chatThreads().length === 0" class="text-center py-8">
            <p class="text-xs" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">Aucune conversation</p>
          </div>
        </div>
      </aside>

      <!-- Main Chat Panel -->
      <main class="flex-1 flex flex-col">
        <!-- Header -->
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
          <!-- Welcome -->
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

        <!-- Input -->
        <div class="px-4 py-4 border-t flex-shrink-0 transition-colors"
          [class]="isDark() ? 'bg-[#0F172A]/60 border-slate-800' : 'bg-white border-slate-200'">
          <form (ngSubmit)="sendMessage()" class="flex items-end gap-3 max-w-3xl mx-auto">
            <div class="flex-1 relative">
              <textarea [(ngModel)]="newMessage" name="msg" rows="1"
                [placeholder]="isSessionResolved() ? 'Session terminée' : 'Écrivez votre message...'"
                [disabled]="isSessionResolved()"
                class="w-full px-4 py-3 rounded-xl text-sm transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500/50 resize-none disabled:opacity-50"
                [class]="isDark() ? 'bg-slate-800/50 border border-slate-700 text-white placeholder-slate-500' : 'bg-slate-50 border border-slate-200 text-slate-900 placeholder-slate-400'"
                (keydown.enter)="$any($event).shiftKey ? null : onEnter($event)"></textarea>
            </div>
            <button type="submit" [disabled]="!newMessage.trim() || isSessionResolved()"
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

  sessionId = '';
  private socket$: WebSocketSubject<any> | null = null;
  private streamingContent = '';

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
    private router: Router
  ) { }

  isDark = () => this.themeService.isDark();
  toggleTheme = () => this.themeService.toggleTheme();

  ngOnInit(): void {
    this.loadChatThreads();
    this.createNewChat();
  }

  ngAfterViewChecked(): void {
    this.scrollToBottom();
  }

  // ─── Multi-Chat ───

  loadChatThreads(): void {
    this.http.get<ChatThread[]>(`${environment.apiUrl}/api/v1/sessions/user-chats`).subscribe({
      next: (chats) => this.chatThreads.set(chats),
      error: () => {}
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

    this.http.post<{ session_id: string }>(`${environment.apiUrl}/api/v1/sessions/create`, {}).subscribe({
      next: (res) => {
        this.sessionId = res.session_id;
        this.connectWebSocket();
        this.loadChatThreads();
      },
      error: (err) => console.error('Failed to create session:', err)
    });
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
    const wsUrl = `${environment.wsUrl.replace('/events', '')}/chat/${this.sessionId}`;
    this.socket$ = webSocket({ url: wsUrl, deserializer: (e) => JSON.parse(e.data) });

    this.socket$.subscribe({
      next: (msg) => this.handleWsMessage(msg),
      error: (err) => { console.error('WS error:', err); this.isConnected.set(false); },
      complete: () => this.isConnected.set(false),
    });

    this.socket$!.next({ type: 'user_connect' });
  }

  private handleWsMessage(msg: any): void {
    switch (msg.type) {
      case 'connected':
        this.isConnected.set(true);
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
        const msgs = this.messages();
        const last = msgs[msgs.length - 1];
        if (last?.isStreaming) {
          this.messages.set([...msgs.slice(0, -1), { ...last, content: this.streamingContent }]);
        } else {
          this.messages.set([...msgs, { role: 'assistant', content: this.streamingContent, isStreaming: true }]);
        }
        break;
      case 'ai_done':
        this.isThinking.set(false);
        const updated = this.messages();
        const lastMsg = updated[updated.length - 1];
        if (lastMsg?.isStreaming) {
          this.messages.set([...updated.slice(0, -1), {
            ...lastMsg,
            isStreaming: false,
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
        this.messages.update(m => [...m, { role: 'system', content: 'Session résolue. Merci d\'avoir contacté I-Way.' }]);
        this.isSessionResolved.set(true);
        this.loadChatThreads();
        break;
    }
  }

  sendMessage(): void {
    if (!this.newMessage.trim() || !this.socket$) return;
    const content = this.newMessage.trim();
    this.newMessage = '';
    this.messages.update(m => [...m, { role: 'user', content }]);
    this.socket$.next({ type: 'user_message', content });
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
    this.socket$?.complete();
  }
}
