import { Component, OnInit, OnDestroy, signal, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
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

interface QueueItem {
  id: string;
  user_name: string;
  user_role: string;
  user_matricule: string;
  status: string;
  created_at: string;
  reason: string | null;
  message_count: number;
  last_message: string;
  agent_matricule: string | null;
}

interface ChatMessage {
  role: 'user' | 'assistant' | 'agent' | 'system';
  content: string;
  timestamp?: string;
}

@Component({
  selector: 'app-agent-workspace',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="h-screen flex transition-colors duration-300"
      [class]="isDark() ? 'bg-[#020617]' : 'bg-slate-50'">

      <!-- Left Panel: Escalation Queue -->
      <aside class="w-80 flex flex-col border-r flex-shrink-0 transition-colors"
        [class]="isDark() ? 'bg-[#0F172A] border-slate-800' : 'bg-white border-slate-200'">
        <!-- Header -->
        <div class="h-16 flex items-center justify-between px-5 border-b flex-shrink-0"
          [class]="isDark() ? 'border-slate-800' : 'border-slate-200'">
          <div class="flex items-center gap-2.5">
            <div class="w-8 h-8 bg-gradient-to-br from-amber-500 to-orange-600 rounded-lg flex items-center justify-center">
              <svg class="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/></svg>
            </div>
            <span class="text-sm font-bold" style="font-family: 'Figtree', sans-serif;"
              [class]="isDark() ? 'text-white' : 'text-slate-900'">Agent Console</span>
          </div>
          <div class="flex items-center gap-1.5">
            <button (click)="toggleTheme()" class="w-8 h-8 rounded-lg flex items-center justify-center transition-colors cursor-pointer"
              [class]="isDark() ? 'hover:bg-slate-800 text-slate-500' : 'hover:bg-slate-100 text-slate-400'">
              <svg *ngIf="isDark()" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"/></svg>
              <svg *ngIf="!isDark()" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"/></svg>
            </button>
            <button (click)="logout()" class="w-8 h-8 rounded-lg flex items-center justify-center transition-colors cursor-pointer"
              [class]="isDark() ? 'hover:bg-slate-800 text-slate-500 hover:text-rose-400' : 'hover:bg-slate-100 text-slate-400 hover:text-rose-500'">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9"/></svg>
            </button>
          </div>
        </div>

        <!-- Queue Label -->
        <div class="px-5 py-3 flex items-center justify-between">
          <span class="text-[10px] font-semibold uppercase tracking-wider" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">Escalation Queue</span>
          <span class="px-2 py-0.5 rounded-md text-[10px] font-bold"
            [class]="isDark() ? 'bg-rose-500/10 text-rose-400' : 'bg-rose-50 text-rose-500'">
            {{queue().length}}
          </span>
        </div>

        <!-- Queue Items -->
        <div class="flex-1 overflow-y-auto px-3 space-y-1.5 custom-scrollbar">
          <div *ngIf="queue().length === 0" class="text-center py-12">
            <svg class="w-10 h-10 mx-auto mb-3" [class]="isDark() ? 'text-slate-700' : 'text-slate-300'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"/></svg>
            <p class="text-xs font-medium" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">No pending escalations</p>
          </div>

          <button *ngFor="let item of queue()" (click)="selectSession(item)"
            class="w-full text-left p-3.5 rounded-xl border transition-all cursor-pointer"
            [class]="getQueueItemClass(item)">
            <div class="flex items-center justify-between mb-1.5">
              <span class="text-xs font-semibold" [class]="isDark() ? 'text-white' : 'text-slate-900'">{{item.user_name}}</span>
              <span class="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase"
                [class]="getStatusBadge(item.status)">{{item.status === 'handoff_pending' ? 'URGENT' : item.status === 'agent_connected' ? 'ACTIVE' : 'AUTO'}}</span>
            </div>
            <p class="text-[11px] truncate mb-1.5" [class]="isDark() ? 'text-slate-500' : 'text-slate-500'">
              {{item.reason || item.last_message || 'No messages yet'}}
            </p>
            <div class="flex items-center justify-between">
              <span class="text-[10px]" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">{{item.message_count}} msgs</span>
              <span class="text-[10px]" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">{{formatTime(item.created_at)}}</span>
            </div>
          </button>
        </div>
      </aside>

      <!-- Right Panel: Agent Chat -->
      <main class="flex-1 flex flex-col">
        <!-- Empty State -->
        <div *ngIf="!activeSession()" class="flex-1 flex items-center justify-center">
          <div class="text-center">
            <div class="w-20 h-20 mx-auto rounded-2xl flex items-center justify-center mb-5"
              [class]="isDark() ? 'bg-slate-800/50' : 'bg-slate-100'">
              <svg class="w-10 h-10" [class]="isDark() ? 'text-slate-700' : 'text-slate-300'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155"/></svg>
            </div>
            <h3 class="text-lg font-bold mb-2" style="font-family: 'Figtree', sans-serif;"
              [class]="isDark() ? 'text-slate-400' : 'text-slate-600'">Select a case from the queue</h3>
            <p class="text-sm" [class]="isDark() ? 'text-slate-600' : 'text-slate-400'">Click on an escalation to view the conversation and take action.</p>
          </div>
        </div>

        <!-- Active Session -->
        <ng-container *ngIf="activeSession()">
          <!-- Session Header -->
          <header class="h-16 flex items-center justify-between px-6 border-b flex-shrink-0"
            [class]="isDark() ? 'bg-[#0F172A]/60 border-slate-800' : 'bg-white border-slate-200'">
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xs font-bold text-white"
                style="background: linear-gradient(135deg, #f59e0b, #ef4444);">
                {{getInitials(activeSession()!.user_name)}}
              </div>
              <div>
                <div class="text-sm font-semibold" [class]="isDark() ? 'text-white' : 'text-slate-900'">{{activeSession()!.user_name}}</div>
                <div class="text-[10px]" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">{{activeSession()!.user_role}} · {{activeSession()!.user_matricule}}</div>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button *ngIf="!hasTakenOver()" (click)="takeoverSession()" [disabled]="isTakingOver()"
                class="px-4 py-2 rounded-xl text-xs font-semibold transition-colors cursor-pointer flex items-center gap-1.5 bg-amber-500 hover:bg-amber-400 text-white disabled:opacity-50">
                <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.042 21.672L13.684 16.6m0 0l-2.51 2.225.569-9.47 5.227 7.917-3.286-.672zM12 2.25V4.5m5.834.166l-1.591 1.591M20.25 10.5H18M7.757 14.743l-1.59 1.59M6 10.5H3.75m4.007-4.243l-1.59-1.59"/></svg>
                {{isTakingOver() ? 'Taking over...' : 'Take Over'}}
              </button>
              <button *ngIf="hasTakenOver()" (click)="resolveSession()"
                class="px-4 py-2 rounded-xl text-xs font-semibold transition-colors cursor-pointer flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white">
                <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                Resolve
              </button>
            </div>
          </header>

          <!-- Chat History -->
          <div #chatContainer class="flex-1 overflow-y-auto px-6 py-4 space-y-3 custom-scrollbar">
            <div *ngFor="let msg of chatHistory()" [ngSwitch]="msg.role">
              <!-- System -->
              <div *ngSwitchCase="'system'" class="flex justify-center">
                <span class="px-3 py-1.5 rounded-full text-[10px] font-medium"
                  [class]="isDark() ? 'bg-slate-800/50 text-slate-500' : 'bg-slate-100 text-slate-500'">{{msg.content}}</span>
              </div>
              <!-- User -->
              <div *ngSwitchCase="'user'" class="flex justify-start gap-2">
                <div class="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 mt-1 text-[9px] font-bold text-white" style="background: #6366f1;">U</div>
                <div class="max-w-[70%] px-3.5 py-2.5 rounded-xl rounded-bl-md text-sm"
                  [class]="isDark() ? 'bg-indigo-500/10 border border-indigo-500/20 text-indigo-200' : 'bg-indigo-50 border border-indigo-100 text-indigo-900'">
                  {{msg.content}}
                </div>
              </div>
              <!-- AI -->
              <div *ngSwitchCase="'assistant'" class="flex justify-start gap-2">
                <div class="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 mt-1 text-[9px] font-bold"
                  [class]="isDark() ? 'bg-slate-800 text-slate-400' : 'bg-slate-200 text-slate-500'">AI</div>
                <div class="max-w-[70%] px-3.5 py-2.5 rounded-xl rounded-bl-md text-sm"
                  [class]="isDark() ? 'bg-slate-800/50 border border-slate-700 text-slate-300' : 'bg-slate-50 border border-slate-200 text-slate-700'">
                  {{msg.content}}
                </div>
              </div>
              <!-- Agent -->
              <div *ngSwitchCase="'agent'" class="flex justify-end">
                <div class="max-w-[70%] px-3.5 py-2.5 rounded-xl rounded-br-md text-sm bg-amber-500 text-white">
                  {{msg.content}}
                </div>
              </div>
            </div>
          </div>

          <!-- Agent Input (only after takeover) -->
          <div *ngIf="hasTakenOver()" class="px-6 py-4 border-t flex-shrink-0"
            [class]="isDark() ? 'bg-[#0F172A]/60 border-slate-800' : 'bg-white border-slate-200'">
            <form (ngSubmit)="sendAgentMessage()" class="flex items-center gap-3">
              <input [(ngModel)]="agentMessage" name="agentMsg" placeholder="Type your response..."
                class="flex-1 px-4 py-3 rounded-xl text-sm transition-all focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                [class]="isDark() ? 'bg-slate-800/50 border border-slate-700 text-white placeholder-slate-500' : 'bg-slate-50 border border-slate-200 text-slate-900 placeholder-slate-400'" />
              <button type="submit" [disabled]="!agentMessage.trim()"
                class="w-11 h-11 bg-amber-500 hover:bg-amber-400 disabled:opacity-30 rounded-xl flex items-center justify-center text-white transition-all cursor-pointer disabled:cursor-not-allowed">
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

  queue = signal<QueueItem[]>([]);
  activeSession = signal<QueueItem | null>(null);
  chatHistory = signal<ChatMessage[]>([]);
  hasTakenOver = signal(false);
  isTakingOver = signal(false);
  agentMessage = '';

  private eventSub?: Subscription;
  private sessionSocket$: WebSocketSubject<any> | null = null;

  constructor(
    private authService: AuthService,
    private themeService: ThemeService,
    private wsService: WebSocketService,
    private http: HttpClient,
    private router: Router
  ) {}

  isDark = () => this.themeService.isDark();
  toggleTheme = () => this.themeService.toggleTheme();

  getInitials(name: string): string {
    return name.split(' ').map(w => w[0] || '').join('').slice(0, 2).toUpperCase();
  }

  ngOnInit(): void {
    this.loadQueue();
    this.wsService.connect();
    // Listen for real-time escalation events
    this.eventSub = this.wsService.getMessages().subscribe(msg => {
      if (msg.type === 'NEW_ESCALATION') {
        this.loadQueue(); // Refresh queue
      } else if (msg.type === 'SESSION_RESOLVED' || msg.type === 'AGENT_JOINED') {
        this.loadQueue();
      }
    });
  }

  private loadQueue(): void {
    this.http.get<QueueItem[]>(`${environment.apiUrl}/api/v1/sessions/active`).subscribe({
      next: (items) => this.queue.set(items),
      error: (err) => console.error('Failed to load queue:', err)
    });
  }

  selectSession(item: QueueItem): void {
    this.activeSession.set(item);
    this.hasTakenOver.set(item.status === 'agent_connected');
    this.loadHistory(item.id);
    // Disconnect previous session socket
    this.sessionSocket$?.complete();
    this.sessionSocket$ = null;
  }

  private loadHistory(sessionId: string): void {
    this.http.get<any>(`${environment.apiUrl}/api/v1/sessions/${sessionId}/history`).subscribe({
      next: (data) => {
        this.chatHistory.set(data.history || []);
        setTimeout(() => this.scrollChat(), 100);
      }
    });
  }

  takeoverSession(): void {
    const session = this.activeSession();
    if (!session) return;
    this.isTakingOver.set(true);

    this.http.post<any>(`${environment.apiUrl}/api/v1/sessions/${session.id}/takeover`, {}).subscribe({
      next: () => {
        this.hasTakenOver.set(true);
        this.isTakingOver.set(false);
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

    // Identify as agent
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
    this.http.post<any>(`${environment.apiUrl}/api/v1/sessions/${session.id}/resolve`, {}).subscribe({
      next: () => {
        this.activeSession.set(null);
        this.chatHistory.set([]);
        this.hasTakenOver.set(false);
        this.sessionSocket$?.complete();
        this.sessionSocket$ = null;
        this.loadQueue();
      }
    });
  }

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

  formatTime(iso: string): string {
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    } catch { return ''; }
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/login']);
  }

  private scrollChat(): void {
    try { this.chatContainer.nativeElement.scrollTop = this.chatContainer.nativeElement.scrollHeight; } catch {}
  }

  ngOnDestroy(): void {
    this.eventSub?.unsubscribe();
    this.sessionSocket$?.complete();
    this.wsService.disconnect();
  }
}
