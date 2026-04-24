import { Component, OnInit, OnDestroy, signal, ViewChild, ElementRef } from '@angular/core';
import { trigger, transition, style, animate } from '@angular/animations';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { Subscription } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from '../../core/services/auth.service';
import { ThemeService } from '../../core/services/theme.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { ToastService } from '../../core/services/toast.service';
import { IwayLogoComponent } from '../../shared/components/iway-logo.component';
import { ConfidenceGaugeComponent } from '../../shared/components/confidence-gauge.component';

import { QueueItem } from '../../shared/models/chat.interface';

interface ChatMessage {
  role: 'user' | 'assistant' | 'agent' | 'system';
  content: string;
  timestamp?: string;
  confidence?: number;
  is_handoff_ai?: boolean;
}

interface Briefing {
  client: { name: string; role: string; matricule: string };
  escalation_reason: string | null;
  ai_summary: string;
  topics: string[];
  duration_minutes: number;
  message_count: number;
  last_ai_confidence: number | null;
  trigger_message: { content: string; confidence: number; query?: string } | null;
  status: string;
}

type QueueFilter = 'all' | 'urgent' | 'active' | 'mine';

@Component({
  selector: 'app-agent-workspace',
  standalone: true,
  imports: [CommonModule, FormsModule, IwayLogoComponent, ConfidenceGaugeComponent],
  animations: [
    trigger('listAnimation', [
      transition(':enter', [
        style({ opacity: 0, transform: 'translateY(-10px)' }),
        animate('300ms ease-out', style({ opacity: 1, transform: 'translateY(0)' }))
      ])
    ])
  ],
  template: `
    <div class="h-screen flex transition-colors duration-300 relative overflow-hidden"
      [class]="isDark() ? 'bg-[#020617]' : 'bg-slate-50'">

      <!-- Mobile Backdrop -->
      <div *ngIf="isSidebarOpen()" (click)="toggleSidebar()"
           class="fixed inset-0 bg-black/50 z-40 md:hidden transition-opacity duration-300"></div>

      <!-- Left Panel: Escalation Queue -->
      <aside class="w-80 flex flex-col border-r flex-shrink-0 transition-transform duration-300 ease-in-out absolute md:relative z-50 h-full shadow-2xl md:shadow-none"
        [class.translate-x-0]="isSidebarOpen()"
        [class.-translate-x-full]="!isSidebarOpen() && !isDesktopMode"
        [class]="isDark() ? 'bg-[#0F172A] border-slate-800' : 'bg-white border-slate-200'">
        <!-- Header -->
        <div class="h-14 flex items-center justify-between px-4 border-b flex-shrink-0"
          [class]="isDark() ? 'border-slate-800' : 'border-slate-200'">
          <div class="flex items-center gap-2">
            <div style="width: 110px;">
              <app-iway-logo [dark]="isDark()" width="100%"></app-iway-logo>
            </div>
          </div>
          <div class="flex items-center gap-1">
            <button (click)="toggleSidebar()" class="md:hidden w-7 h-7 rounded-lg flex items-center justify-center transition-colors cursor-pointer mr-1"
              [class]="isDark() ? 'hover:bg-slate-800 text-slate-400' : 'hover:bg-slate-100 text-slate-500'">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
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

        <!-- Filter Tabs -->
        <div class="px-3 py-2.5 flex gap-1 border-b"
          [class]="isDark() ? 'border-slate-800' : 'border-slate-200'">
          <button *ngFor="let f of filterOptions" (click)="setFilter(f.key)"
            class="flex-1 px-2 py-1.5 rounded-lg text-[10px] font-semibold transition-all cursor-pointer flex items-center justify-center gap-1"
            [class]="currentFilter() === f.key
              ? (isDark() ? 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/30' : 'bg-indigo-50 text-indigo-600 border border-indigo-200')
              : (isDark() ? 'text-slate-500 hover:bg-slate-800/50 border border-transparent' : 'text-slate-400 hover:bg-slate-50 border border-transparent')">
            {{f.label}}
            <span *ngIf="getFilterCount(f.key) > 0" class="px-1 py-0 rounded text-[8px] font-bold"
              [class]="currentFilter() === f.key
                ? (isDark() ? 'bg-indigo-500/20 text-indigo-300' : 'bg-indigo-100 text-indigo-700')
                : (isDark() ? 'bg-slate-700 text-slate-400' : 'bg-slate-100 text-slate-500')">
              {{getFilterCount(f.key)}}
            </span>
          </button>
        </div>

        <!-- Search -->
        <div class="px-3 py-2">
          <input [(ngModel)]="searchQuery" placeholder="Rechercher par nom ou raison..."
            class="w-full px-3 py-2 rounded-lg text-[11px] transition-all focus:outline-none focus:ring-1 focus:ring-indigo-500/50"
            [class]="isDark() ? 'bg-slate-800/50 border border-slate-700 text-white placeholder-slate-500' : 'bg-slate-50 border border-slate-200 text-slate-900 placeholder-slate-400'" />
        </div>

        <!-- Queue Items -->
        <div class="flex-1 overflow-y-auto px-3 space-y-1.5 custom-scrollbar">
          <div *ngIf="filteredQueue().length === 0 && !queueLoading()" class="text-center py-10">
            <svg class="w-8 h-8 mx-auto mb-2" [class]="isDark() ? 'text-slate-700' : 'text-slate-300'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"/></svg>
            <p class="text-[11px]" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">Aucune escalation</p>
          </div>

          <!-- Skeleton loader -->
          <div *ngIf="queueLoading()" class="space-y-2">
            <div *ngFor="let s of [1,2,3]" class="p-3 rounded-xl border animate-pulse"
              [class]="isDark() ? 'bg-slate-800/30 border-slate-700/50' : 'bg-slate-50 border-slate-200'">
              <div class="flex items-center gap-2 mb-2">
                <div class="w-2 h-2 rounded-full" [class]="isDark() ? 'bg-slate-700' : 'bg-slate-200'"></div>
                <div class="h-3 rounded w-24" [class]="isDark() ? 'bg-slate-700' : 'bg-slate-200'"></div>
                <div class="ml-auto h-3 rounded w-12" [class]="isDark() ? 'bg-slate-700' : 'bg-slate-200'"></div>
              </div>
              <div class="h-2.5 rounded w-full mb-1.5" [class]="isDark() ? 'bg-slate-700/60' : 'bg-slate-100'"></div>
              <div class="flex justify-between">
                <div class="h-2 rounded w-10" [class]="isDark() ? 'bg-slate-700/40' : 'bg-slate-100'"></div>
                <div class="h-2 rounded w-14" [class]="isDark() ? 'bg-slate-700/40' : 'bg-slate-100'"></div>
              </div>
            </div>
          </div>

          <button *ngFor="let item of filteredQueue()" (click)="selectSession(item)" @listAnimation
            class="w-full text-left p-3 rounded-xl border transition-all cursor-pointer"
            [class]="getQueueItemClass(item)">
            <div class="flex items-center justify-between mb-1">
              <div class="flex items-center gap-1.5">
                <span class="w-2 h-2 rounded-full flex-shrink-0"
                  [class]="item.status === 'handoff_pending' ? 'bg-rose-500 animate-pulse' : item.status === 'agent_connected' ? 'bg-emerald-500' : 'bg-slate-400'"></span>
                <span class="text-xs font-semibold" [class]="isDark() ? 'text-white' : 'text-slate-900'">{{item.user_name}}</span>
              </div>
              <span class="px-1.5 py-0.5 rounded text-[8px] font-bold uppercase"
                [class]="getStatusBadge(item.status)">{{getStatusLabel(item.status)}}</span>
            </div>
            <p class="text-[10px] truncate mb-1" [class]="isDark() ? 'text-slate-500' : 'text-slate-500'">
              {{item.reason || item.last_message || 'Pas de messages'}}
            </p>
            <div class="flex items-center justify-between">
              <span class="text-[9px]" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">{{item.message_count}} msgs</span>
              <div class="flex items-center gap-2">
                <span *ngIf="item.last_ai_confidence !== null" class="text-[9px] px-1.5 py-0.5 rounded"
                  [class]="getConfidenceClass(item.last_ai_confidence)">
                  {{item.last_ai_confidence}}%
                </span>
                <span class="text-[9px]" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">{{formatTime(item.created_at)}}</span>
              </div>
            </div>
          </button>
        </div>
      </aside>

      <!-- Right Panel -->
      <main class="flex-1 flex flex-col min-w-0 relative h-full">
        <!-- Mobile Header (when no active session) -->
        <header *ngIf="!activeSession()" class="md:hidden h-14 flex items-center px-4 border-b flex-shrink-0" [class]="isDark() ? 'bg-[#0F172A]/80 border-slate-800' : 'bg-white border-slate-200'">
          <button (click)="toggleSidebar()" class="p-2 -ml-2 rounded-lg transition-colors cursor-pointer" [class]="isDark() ? 'hover:bg-slate-800 text-slate-300' : 'hover:bg-slate-100 text-slate-700'" aria-label="Ouvrir la file d'attente">
            <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/></svg>
          </button>
          <span class="ml-2 text-sm font-semibold" [class]="isDark() ? 'text-slate-200' : 'text-slate-800'">File d'attente</span>
        </header>

        <!-- Empty State -->
        <div *ngIf="!activeSession()" class="flex-1 flex items-center justify-center">
          <div class="text-center">
            <div class="w-16 h-16 mx-auto rounded-2xl flex items-center justify-center mb-4"
              [class]="isDark() ? 'bg-slate-800/50' : 'bg-slate-100'">
              <svg class="w-8 h-8" [class]="isDark() ? 'text-slate-700' : 'text-slate-300'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155"/></svg>
            </div>
            <h3 class="text-base font-bold mb-1" style="font-family: 'Figtree', sans-serif;"
              [class]="isDark() ? 'text-slate-400' : 'text-slate-600'">Sélectionnez un cas</h3>
            <p class="text-xs" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">Cliquez sur une escalation pour voir la conversation.</p>
          </div>
        </div>

        <!-- Active Session -->
        <ng-container *ngIf="activeSession()">
          <!-- Session Header -->
          <header class="h-14 flex items-center justify-between px-3 md:px-5 border-b flex-shrink-0"
            [class]="isDark() ? 'bg-[#0F172A]/60 border-slate-800' : 'bg-white border-slate-200'">
            <div class="flex items-center gap-2 md:gap-3 min-w-0">
              <button (click)="toggleSidebar()" class="md:hidden p-1.5 -ml-1 rounded-lg transition-colors cursor-pointer flex-shrink-0" [class]="isDark() ? 'hover:bg-slate-800 text-slate-300' : 'hover:bg-slate-100 text-slate-700'" aria-label="Ouvrir la file d'attente">
                <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/></svg>
              </button>
              <div class="w-8 h-8 rounded-xl flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
                style="background: linear-gradient(135deg, #f59e0b, #ef4444);">
                {{getInitials(activeSession()!.user_name)}}
              </div>
              <div>
                <div class="text-sm font-semibold" [class]="isDark() ? 'text-white' : 'text-slate-900'">{{activeSession()!.user_name}}</div>
                <div class="text-[10px]" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">{{activeSession()!.user_role}} · {{activeSession()!.user_matricule}}</div>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button (click)="toggleBriefing()" class="px-3 py-1.5 rounded-lg text-[10px] font-semibold transition-colors cursor-pointer flex items-center gap-1"
                [class]="showBriefing()
                  ? (isDark() ? 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/30' : 'bg-indigo-50 text-indigo-600 border border-indigo-200')
                  : (isDark() ? 'bg-slate-800 text-slate-400 hover:bg-slate-700' : 'bg-slate-100 text-slate-600 hover:bg-slate-200')">
                <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z"/></svg>
                Briefing
              </button>
              <button *ngIf="!hasTakenOver()" (click)="takeoverSession()" [disabled]="isTakingOver()"
                class="px-3 py-1.5 rounded-lg text-[10px] font-semibold transition-colors cursor-pointer flex items-center gap-1 bg-amber-500 hover:bg-amber-400 text-white disabled:opacity-50">
                <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.042 21.672L13.684 16.6m0 0l-2.51 2.225.569-9.47 5.227 7.917-3.286-.672zM12 2.25V4.5m5.834.166l-1.591 1.591M20.25 10.5H18M7.757 14.743l-1.59 1.59M6 10.5H3.75m4.007-4.243l-1.59-1.59"/></svg>
                {{isTakingOver() ? 'Prise en charge...' : 'Prendre en charge'}}
              </button>
              <button *ngIf="hasTakenOver()" (click)="showResolveDialog.set(true)"
                class="px-3 py-1.5 rounded-lg text-[10px] font-semibold transition-colors cursor-pointer flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/50">
                <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                Résoudre
              </button>
            </div>
          </header>

          <!-- Resolve Dialog (inline panel) -->
          <div *ngIf="showResolveDialog()" class="border-b overflow-hidden transition-all"
            [class]="isDark() ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-emerald-50 border-emerald-200'">
            <div class="px-5 py-4">
              <div class="flex items-center gap-2 mb-3">
                <svg class="w-4 h-4" [class]="isDark() ? 'text-emerald-400' : 'text-emerald-600'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                <span class="text-xs font-bold" [class]="isDark() ? 'text-emerald-300' : 'text-emerald-800'">Résoudre cette session</span>
              </div>
              <label class="flex items-center gap-2 mb-3 cursor-pointer">
                <input type="checkbox" [(ngModel)]="saveToKnowledge" class="w-3.5 h-3.5 rounded border accent-emerald-500 cursor-pointer"
                  [class]="isDark() ? 'border-slate-600' : 'border-slate-300'" />
                <span class="text-[11px] font-medium" [class]="isDark() ? 'text-slate-300' : 'text-slate-700'">Sauvegarder dans la base de connaissances (HITL)</span>
              </label>
              <div *ngIf="saveToKnowledge" class="mb-3">
                <input [(ngModel)]="resolveTags" placeholder="Tags (séparés par virgule, ex: dentaire, remboursement)"
                  class="w-full px-3 py-2 rounded-lg text-[11px] transition-all focus:outline-none focus:ring-1 focus:ring-emerald-500/50"
                  [class]="isDark() ? 'bg-slate-800/50 border border-slate-700 text-white placeholder-slate-500' : 'bg-white border border-slate-200 text-slate-900 placeholder-slate-400'" />
              </div>
              <div class="flex items-center gap-2">
                <button (click)="resolveSession()"
                  class="px-4 py-2 rounded-lg text-[10px] font-semibold cursor-pointer transition-colors bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500/50">
                  <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.5 12.75l6 6 9-13.5"/></svg>
                  Confirmer
                </button>
                <button (click)="showResolveDialog.set(false)"
                  class="px-4 py-2 rounded-lg text-[10px] font-semibold cursor-pointer transition-colors flex items-center gap-1 focus:outline-none focus:ring-2 focus:ring-slate-500/50"
                  [class]="isDark() ? 'bg-slate-800 text-slate-400 hover:bg-slate-700' : 'bg-white text-slate-600 hover:bg-slate-50 border border-slate-200'">
                  Annuler
                </button>
              </div>
            </div>
          </div>

          <!-- Briefing Panel (collapsible) -->
          <div *ngIf="showBriefing() && briefing()" class="border-b overflow-hidden transition-all"
            [class]="isDark() ? 'bg-[#0F172A]/40 border-slate-800' : 'bg-slate-50 border-slate-200'">
            <div class="px-5 py-4">
              <!-- Client Info + Stats Row -->
              <div class="flex items-start gap-4 mb-3">
                <div class="flex-1">
                  <div class="flex items-center gap-2 mb-2">
                    <span class="text-[10px] font-bold uppercase tracking-wider" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">Résumé IA</span>
                    <span *ngIf="briefingLoading()" class="text-[9px] animate-pulse" [class]="isDark() ? 'text-indigo-400' : 'text-indigo-500'">Chargement...</span>
                  </div>
                  <p class="text-xs leading-relaxed" [class]="isDark() ? 'text-slate-300' : 'text-slate-700'">
                    {{briefing()!.ai_summary}}
                  </p>
                </div>
                <div class="flex flex-col gap-1.5 flex-shrink-0 items-end">
                  <app-confidence-gauge *ngIf="briefing()!.last_ai_confidence !== null"
                    [value]="briefing()!.last_ai_confidence!" [size]="72" [strokeWidth]="5"></app-confidence-gauge>
                  <div class="flex items-center gap-1.5">
                    <span class="text-[9px]" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">Durée</span>
                    <span class="px-1.5 py-0.5 rounded text-[9px] font-bold" [class]="isDark() ? 'bg-slate-800 text-slate-300' : 'bg-white text-slate-700'">
                      {{briefing()!.duration_minutes}} min
                    </span>
                  </div>
                  <div class="flex items-center gap-1.5">
                    <span class="text-[9px]" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">Messages</span>
                    <span class="px-1.5 py-0.5 rounded text-[9px] font-bold" [class]="isDark() ? 'bg-slate-800 text-slate-300' : 'bg-white text-slate-700'">
                      {{briefing()!.message_count}}
                    </span>
                  </div>
                </div>
              </div>

              <!-- Topics -->
              <div *ngIf="briefing()!.topics.length > 0" class="flex items-center gap-1.5 mb-3">
                <span class="text-[9px] font-semibold" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">Sujets:</span>
                <span *ngFor="let topic of briefing()!.topics" class="px-2 py-0.5 rounded-full text-[9px] font-medium"
                  [class]="isDark() ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20' : 'bg-indigo-50 text-indigo-600 border border-indigo-200'">
                  {{topic}}
                </span>
              </div>

              <!-- Trigger Message (AI response that caused escalation) -->
              <div *ngIf="briefing()!.trigger_message" class="rounded-xl p-3 border"
                [class]="isDark() ? 'bg-rose-500/5 border-rose-500/20' : 'bg-rose-50 border-rose-200'">
                <div class="flex items-center justify-between mb-2">
                  <span class="text-[9px] font-bold uppercase tracking-wider" [class]="isDark() ? 'text-rose-400' : 'text-rose-600'">
                    Réponse IA ayant déclenché l'escalade ({{briefing()!.trigger_message!.confidence}}%)
                  </span>
                </div>
                <p class="text-xs mb-3" [class]="isDark() ? 'text-rose-200/80' : 'text-rose-800'">
                  "{{briefing()!.trigger_message!.content}}"
                </p>
                <div class="flex items-center gap-2">
                  <button (click)="approveAiResponse()" class="px-3 py-1.5 rounded-lg text-[10px] font-semibold cursor-pointer transition-colors bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-1">
                    <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.5 12.75l6 6 9-13.5"/></svg>
                    Approuver et envoyer
                  </button>
                  <button (click)="showClarifyInput.set(true)" *ngIf="!showClarifyInput()"
                    class="px-3 py-1.5 rounded-lg text-[10px] font-semibold cursor-pointer transition-colors flex items-center gap-1"
                    [class]="isDark() ? 'bg-slate-800 text-slate-300 hover:bg-slate-700' : 'bg-white text-slate-700 hover:bg-slate-50 border border-slate-200'">
                    <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"/></svg>
                    Clarifier
                  </button>
                </div>
                <!-- Clarify Input -->
                <div *ngIf="showClarifyInput()" class="mt-2 flex gap-2">
                  <input [(ngModel)]="clarifyText" placeholder="Ajoutez votre précision..."
                    class="flex-1 px-3 py-2 rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-amber-500/50"
                    [class]="isDark() ? 'bg-slate-800 border border-slate-700 text-white placeholder-slate-500' : 'bg-white border border-slate-200 text-slate-900 placeholder-slate-400'" />
                  <button (click)="clarifyAiResponse()" [disabled]="!clarifyText.trim()"
                    class="px-3 py-2 rounded-lg text-[10px] font-semibold cursor-pointer bg-amber-500 hover:bg-amber-400 text-white disabled:opacity-50">
                    Envoyer
                  </button>
                </div>
              </div>

              <!-- Session Timeline -->
              <div class="mt-4 pt-3 border-t" [class]="isDark() ? 'border-slate-800' : 'border-slate-200'">
                <div class="flex items-center gap-1.5 mb-3">
                  <svg class="w-3 h-3" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  <span class="text-[9px] font-bold uppercase tracking-wider" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">Chronologie</span>
                </div>
                <div class="relative pl-4">
                  <!-- Vertical line -->
                  <div class="absolute left-[5px] top-1 bottom-1 w-px" [class]="isDark() ? 'bg-slate-700' : 'bg-slate-200'"></div>

                  <!-- Event: Chat started -->
                  <div class="relative flex items-start gap-2.5 mb-3">
                    <div class="absolute left-[-13px] top-0.5 w-2.5 h-2.5 rounded-full border-2 flex-shrink-0"
                      [class]="isDark() ? 'bg-indigo-500 border-indigo-400' : 'bg-indigo-500 border-indigo-300'"></div>
                    <div>
                      <span class="text-[10px] font-medium" [class]="isDark() ? 'text-slate-300' : 'text-slate-700'">Chat démarré</span>
                      <span class="text-[9px] ml-1" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">par {{briefing()!.client.name}}</span>
                    </div>
                  </div>

                  <!-- Event: AI responses with confidence -->
                  <div *ngFor="let evt of getTimelineConfidenceEvents()" class="relative flex items-start gap-2.5 mb-3">
                    <div class="absolute left-[-13px] top-0.5 w-2.5 h-2.5 rounded-full border-2 flex-shrink-0"
                      [class]="evt.confidence >= 70 ? 'bg-emerald-500 border-emerald-400' : evt.confidence >= 40 ? 'bg-amber-500 border-amber-400' : 'bg-rose-500 border-rose-400'"></div>
                    <div>
                      <span class="text-[10px] font-medium" [class]="isDark() ? 'text-slate-300' : 'text-slate-700'">IA a répondu</span>
                      <span class="text-[10px] font-bold ml-1"
                        [class]="evt.confidence >= 70 ? 'text-emerald-400' : evt.confidence >= 40 ? 'text-amber-400' : 'text-rose-400'">({{evt.confidence}}%)</span>
                    </div>
                  </div>

                  <!-- Event: Handoff triggered -->
                  <div *ngIf="briefing()!.escalation_reason" class="relative flex items-start gap-2.5 mb-3">
                    <div class="absolute left-[-13px] top-0.5 w-2.5 h-2.5 rounded-full border-2 flex-shrink-0 bg-rose-500 border-rose-400"></div>
                    <div>
                      <span class="text-[10px] font-medium" [class]="isDark() ? 'text-rose-300' : 'text-rose-700'">Handoff déclenché</span>
                      <p class="text-[9px] mt-0.5 truncate max-w-[200px]" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">{{briefing()!.escalation_reason}}</p>
                    </div>
                  </div>

                  <!-- Event: Agent joined -->
                  <div *ngIf="briefing()!.status === 'agent_connected'" class="relative flex items-start gap-2.5">
                    <div class="absolute left-[-13px] top-0.5 w-2.5 h-2.5 rounded-full border-2 flex-shrink-0 bg-emerald-500 border-emerald-400"></div>
                    <div>
                      <span class="text-[10px] font-medium" [class]="isDark() ? 'text-emerald-300' : 'text-emerald-700'">Agent connecté</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Chat History -->
          <div #chatContainer class="flex-1 overflow-y-auto px-5 py-4 space-y-3 custom-scrollbar">
            <div *ngFor="let msg of chatHistory()" [ngSwitch]="msg.role">
              <!-- System -->
              <div *ngSwitchCase="'system'" class="flex justify-center">
                <span class="px-3 py-1.5 rounded-full text-[10px] font-medium"
                  [class]="isDark() ? 'bg-slate-800/50 text-slate-500' : 'bg-slate-100 text-slate-500'">{{msg.content}}</span>
              </div>
              <!-- User -->
              <div *ngSwitchCase="'user'" class="flex justify-start gap-2">
                <div class="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 mt-1 text-[9px] font-bold text-white" style="background: #6366f1;">U</div>
                <div class="max-w-[70%] px-3 py-2.5 rounded-xl rounded-bl-md text-sm"
                  [class]="isDark() ? 'bg-indigo-500/10 border border-indigo-500/20 text-indigo-200' : 'bg-indigo-50 border border-indigo-100 text-indigo-900'">
                  {{msg.content}}
                </div>
              </div>
              <!-- AI -->
              <div *ngSwitchCase="'assistant'" class="flex justify-start gap-2">
                <div class="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 mt-1"
                  [class]="msg.is_handoff_ai
                    ? (isDark() ? 'bg-orange-500/10' : 'bg-orange-100')
                    : (isDark() ? 'bg-slate-800' : 'bg-slate-200')">
                  <svg *ngIf="msg.is_handoff_ai" class="w-3 h-3" [class]="isDark() ? 'text-orange-400' : 'text-orange-600'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  <svg *ngIf="!msg.is_handoff_ai" class="w-3 h-3" [class]="isDark() ? 'text-slate-400' : 'text-slate-500'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/></svg>
                </div>
                <div>
                  <!-- Handoff badge -->
                  <div *ngIf="msg.is_handoff_ai" class="mb-0.5">
                    <span class="text-[8px] font-semibold px-1.5 py-0.5 rounded-full"
                      [class]="isDark() ? 'bg-orange-500/10 text-orange-400' : 'bg-orange-50 text-orange-600'">En attente agent</span>
                  </div>
                  <div class="max-w-[70%] px-3 py-2.5 rounded-xl rounded-bl-md text-sm"
                    [class]="msg.is_handoff_ai
                      ? (isDark() ? 'bg-orange-500/5 border border-orange-500/20 text-orange-200' : 'bg-orange-50 border border-orange-200 text-orange-900')
                      : (isDark() ? 'bg-slate-800/50 border border-slate-700 text-slate-300' : 'bg-slate-50 border border-slate-200 text-slate-700')">
                    {{msg.content}}
                  </div>
                  <!-- Confidence badge -->
                  <div *ngIf="msg.confidence" class="mt-0.5">
                    <span class="text-[8px] font-medium px-1.5 py-0.5 rounded"
                      [class]="getConfidenceClass(msg.confidence)">
                      Confiance: {{msg.confidence}}%
                    </span>
                  </div>
                </div>
              </div>
              <!-- Agent -->
              <div *ngSwitchCase="'agent'" class="flex justify-end">
                <div class="max-w-[70%] px-3 py-2.5 rounded-xl rounded-br-md text-sm bg-amber-500 text-white">
                  {{msg.content}}
                </div>
              </div>
            </div>
          </div>

          <!-- Agent Input (after takeover) -->
          <div *ngIf="hasTakenOver()" class="px-5 py-3 border-t flex-shrink-0"
            [class]="isDark() ? 'bg-[#0F172A]/60 border-slate-800' : 'bg-white border-slate-200'">
            <form (ngSubmit)="sendAgentMessage()" class="flex items-center gap-3">
              <input [(ngModel)]="agentMessage" name="agentMsg" placeholder="Répondre au client..."
                class="flex-1 px-4 py-2.5 rounded-xl text-sm transition-all focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                [class]="isDark() ? 'bg-slate-800/50 border border-slate-700 text-white placeholder-slate-500' : 'bg-slate-50 border border-slate-200 text-slate-900 placeholder-slate-400'" />
              <button type="submit" [disabled]="!agentMessage.trim()"
                class="w-10 h-10 bg-amber-500 hover:bg-amber-400 disabled:opacity-30 rounded-xl flex items-center justify-center text-white transition-all cursor-pointer disabled:cursor-not-allowed">
                <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"/></svg>
              </button>
            </form>
          </div>
        </ng-container>
      </main>
    </div>
  `
})
export class AgentWorkspaceComponent implements OnInit, OnDestroy {
  @ViewChild('chatContainer') private chatContainer!: ElementRef;

  queue = this.wsService.sidebarQueue;
  queueLoading = signal(true);
  activeSession = signal<QueueItem | null>(null);
  chatHistory = signal<ChatMessage[]>([]);
  hasTakenOver = signal(false);
  isTakingOver = signal(false);
  agentMessage = '';
  searchQuery = '';
  isSidebarOpen = signal(false);
  
  get isDesktopMode(): boolean {
    return window.innerWidth >= 768; // md breakpoint
  }

  // Filters
  currentFilter = signal<QueueFilter>('all');
  filterOptions: { key: QueueFilter; label: string }[] = [
    { key: 'all', label: 'Tout' },
    { key: 'urgent', label: 'Urgent' },
    { key: 'active', label: 'Actif' },
    { key: 'mine', label: 'Mes cas' },
  ];

  // Briefing
  showBriefing = signal(false);
  briefing = signal<Briefing | null>(null);
  briefingLoading = signal(false);
  showClarifyInput = signal(false);
  clarifyText = '';

  // Resolve dialog
  showResolveDialog = signal(false);
  saveToKnowledge = false;
  resolveTags = '';

  private eventSub?: Subscription;
  private sessionSocket$: WebSocketSubject<any> | null = null;
  private currentAgentMatricule = '';

  constructor(
    private authService: AuthService,
    private themeService: ThemeService,
    private wsService: WebSocketService,
    private http: HttpClient,
    private router: Router,
    private toastService: ToastService
  ) { }

  isDark = () => this.themeService.isDark();
  toggleTheme = () => this.themeService.toggleTheme();

  toggleSidebar() {
    this.isSidebarOpen.update(v => !v);
  }

  closeSidebarOnMobile() {
    if (!this.isDesktopMode) {
      this.isSidebarOpen.set(false);
    }
  }

  getInitials(name: string): string {
    return name.split(' ').map(w => w[0] || '').join('').slice(0, 2).toUpperCase();
  }

  ngOnInit(): void {
    // Get current agent matricule
    const user = this.authService.getCurrentUser();
    this.currentAgentMatricule = user?.matricule || '';

    this.loadQueue();
    this.wsService.connect();
    this.eventSub = this.wsService.getMessages().subscribe(msg => {
      if (msg.type === 'NEW_ESCALATION') {
        this.toastService.show('Nouvelle escalation reçue', 'warning');
      } else if (msg.type === 'SESSION_RESOLVED') {
        this.toastService.show('Session résolue avec succès', 'success');
      } else if (msg.type === 'AGENT_JOINED') {
        // Optionnel: on peut forcer le rechargement si nécessaire, mais le websocket le gère si sidebar_update est émis.
        // this.loadQueue(); 
      }
    });
  }

  // ─── Queue ───

  private loadQueue(): void {
    this.queueLoading.set(true);
    this.http.get<QueueItem[]>(`${environment.apiUrl}/api/v1/sessions/active`).subscribe({
      next: (items) => { this.wsService.setInitialQueue(items); this.queueLoading.set(false); },
      error: (err) => { console.error('Failed to load queue:', err); this.queueLoading.set(false); }
    });
  }

  filteredQueue(): QueueItem[] {
    let items = this.queue();

    // Apply filter
    switch (this.currentFilter()) {
      case 'urgent':
        items = items.filter(i => i.status === 'handoff_pending');
        break;
      case 'active':
        items = items.filter(i => i.status === 'agent_connected');
        break;
      case 'mine':
        items = items.filter(i => i.agent_matricule === this.currentAgentMatricule);
        break;
    }

    // Apply search
    if (this.searchQuery.trim()) {
      const q = this.searchQuery.toLowerCase();
      items = items.filter(i =>
        i.user_name.toLowerCase().includes(q) ||
        (i.reason || '').toLowerCase().includes(q) ||
        (i.last_message || '').toLowerCase().includes(q)
      );
    }

    return items;
  }

  getFilterCount(filter: QueueFilter): number {
    const items = this.queue();
    switch (filter) {
      case 'all': return items.length;
      case 'urgent': return items.filter(i => i.status === 'handoff_pending').length;
      case 'active': return items.filter(i => i.status === 'agent_connected').length;
      case 'mine': return items.filter(i => i.agent_matricule === this.currentAgentMatricule).length;
    }
  }

  setFilter(filter: QueueFilter): void {
    this.currentFilter.set(filter);
  }

  // ─── Session ───

  selectSession(item: QueueItem): void {
    this.activeSession.set(item);
    this.hasTakenOver.set(item.status === 'agent_connected');
    this.showBriefing.set(false);
    this.briefing.set(null);
    this.showClarifyInput.set(false);
    this.clarifyText = '';
    this.loadHistory(item.id);
    this.sessionSocket$?.complete();
    this.sessionSocket$ = null;
    this.closeSidebarOnMobile();

    // Auto-load briefing for pending sessions
    if (item.status === 'handoff_pending') {
      this.toggleBriefing();
    }
  }

  private loadHistory(sessionId: string): void {
    this.http.get<any>(`${environment.apiUrl}/api/v1/sessions/${sessionId}/history`).subscribe({
      next: (data) => {
        this.chatHistory.set(data.history || []);
        setTimeout(() => this.scrollChat(), 100);
      }
    });
  }

  toggleBriefing(): void {
    if (this.showBriefing()) {
      this.showBriefing.set(false);
      return;
    }

    const session = this.activeSession();
    if (!session) return;

    this.showBriefing.set(true);
    this.briefingLoading.set(true);

    this.http.get<Briefing>(`${environment.apiUrl}/api/v1/sessions/${session.id}/briefing`).subscribe({
      next: (data) => {
        this.briefing.set(data);
        this.briefingLoading.set(false);
      },
      error: () => this.briefingLoading.set(false)
    });
  }

  // ─── Approve / Clarify ───

  approveAiResponse(): void {
    const session = this.activeSession();
    if (!session) return;

    this.http.post<any>(`${environment.apiUrl}/api/v1/sessions/${session.id}/approve`, {
      action: 'approve'
    }).subscribe({
      next: () => {
        this.loadHistory(session.id);
        this.loadQueue();
        // Clear trigger from briefing
        if (this.briefing()) {
          this.briefing.set({ ...this.briefing()!, trigger_message: null });
        }
      }
    });
  }

  clarifyAiResponse(): void {
    const session = this.activeSession();
    if (!session || !this.clarifyText.trim()) return;

    this.http.post<any>(`${environment.apiUrl}/api/v1/sessions/${session.id}/approve`, {
      action: 'clarify',
      clarification: this.clarifyText.trim()
    }).subscribe({
      next: () => {
        this.loadHistory(session.id);
        this.loadQueue();
        this.showClarifyInput.set(false);
        this.clarifyText = '';
        if (this.briefing()) {
          this.briefing.set({ ...this.briefing()!, trigger_message: null });
        }
      }
    });
  }

  // ─── Takeover ───

  takeoverSession(): void {
    const session = this.activeSession();
    if (!session) return;
    this.isTakingOver.set(true);

    this.http.post<any>(`${environment.apiUrl}/api/v1/sessions/${session.id}/takeover`, {}).subscribe({
      next: () => {
        this.hasTakenOver.set(true);
        this.isTakingOver.set(false);
        this.toastService.show('Session prise en charge', 'success');
        this.connectToSessionWs(session.id);
        this.loadHistory(session.id);
        this.loadQueue();
      },
      error: () => this.isTakingOver.set(false)
    });
  }

  private connectToSessionWs(sessionId: string): void {
    const wsUrl = `${environment.wsUrl.replace('/events', '')}/chat/${sessionId}`;
    this.sessionSocket$ = webSocket({ url: wsUrl, deserializer: (e) => JSON.parse(e.data) });

    this.sessionSocket$.subscribe({
      next: (msg) => {
        if (msg.type === 'user_message') {
          this.chatHistory.update(h => [...h, { role: 'user', content: msg.content, timestamp: msg.timestamp }]);
          setTimeout(() => this.scrollChat(), 50);
        }
      }
    });

    this.sessionSocket$.next({ type: 'agent_connect' });
  }

  sendAgentMessage(): void {
    if (!this.agentMessage.trim() || !this.sessionSocket$) return;
    const content = this.agentMessage.trim();
    this.agentMessage = '';
    this.chatHistory.update(h => [...h, { role: 'agent', content }]);
    this.sessionSocket$.next({ type: 'agent_message', content });
    setTimeout(() => this.scrollChat(), 50);
  }

  resolveSession(): void {
    const session = this.activeSession();
    if (!session) return;

    const body: any = {};
    if (this.saveToKnowledge) {
      body.save_to_knowledge = true;
      if (this.resolveTags.trim()) {
        body.tags = this.resolveTags.split(',').map((t: string) => t.trim()).filter((t: string) => t);
      }
    }

    this.http.post<any>(`${environment.apiUrl}/api/v1/sessions/${session.id}/resolve`, body).subscribe({
      next: () => {
        this.toastService.show('Session résolue avec succès', 'success');
        this.activeSession.set(null);
        this.chatHistory.set([]);
        this.hasTakenOver.set(false);
        this.showBriefing.set(false);
        this.briefing.set(null);
        this.showResolveDialog.set(false);
        this.saveToKnowledge = false;
        this.resolveTags = '';
        this.sessionSocket$?.complete();
        this.sessionSocket$ = null;
        this.loadQueue();
      }
    });
  }

  // ─── UI Helpers ───

  getQueueItemClass(item: QueueItem): string {
    const active = this.activeSession()?.id === item.id;
    if (this.isDark()) {
      if (active) return 'bg-slate-800/80 border-indigo-500/50';
      if (item.status === 'handoff_pending') return 'bg-rose-500/5 border-rose-500/20 hover:border-rose-500/40';
      return 'bg-slate-800/30 border-slate-700/50 hover:border-slate-600';
    } else {
      if (active) return 'bg-indigo-50 border-indigo-300';
      if (item.status === 'handoff_pending') return 'bg-rose-50 border-rose-200 hover:border-rose-300';
      return 'bg-white border-slate-200 hover:border-slate-300 shadow-sm';
    }
  }

  getStatusBadge(status: string): string {
    if (this.isDark()) {
      if (status === 'handoff_pending') return 'bg-rose-500/10 text-rose-400';
      if (status === 'agent_connected') return 'bg-emerald-500/10 text-emerald-400';
      return 'bg-slate-700 text-slate-400';
    } else {
      if (status === 'handoff_pending') return 'bg-rose-100 text-rose-600';
      if (status === 'agent_connected') return 'bg-emerald-100 text-emerald-600';
      return 'bg-slate-100 text-slate-500';
    }
  }

  getStatusLabel(status: string): string {
    if (status === 'handoff_pending') return 'URGENT';
    if (status === 'agent_connected') return 'ACTIF';
    return 'AUTO';
  }

  getConfidenceClass(confidence: number): string {
    if (confidence >= 80) return this.isDark() ? 'bg-emerald-500/10 text-emerald-400' : 'bg-emerald-50 text-emerald-700';
    if (confidence >= 50) return this.isDark() ? 'bg-amber-500/10 text-amber-400' : 'bg-amber-50 text-amber-700';
    return this.isDark() ? 'bg-rose-500/10 text-rose-400' : 'bg-rose-50 text-rose-700';
  }

  formatTime(iso: string): string {
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    } catch { return ''; }
  }

  getTimelineConfidenceEvents(): { confidence: number }[] {
    return this.chatHistory()
      .filter(m => m.role === 'assistant' && m.confidence != null)
      .map(m => ({ confidence: m.confidence! }));
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/login']);
  }

  private scrollChat(): void {
    try { this.chatContainer.nativeElement.scrollTop = this.chatContainer.nativeElement.scrollHeight; } catch { }
  }

  ngOnDestroy(): void {
    this.eventSub?.unsubscribe();
    this.sessionSocket$?.complete();
    this.wsService.disconnect();
  }
}
