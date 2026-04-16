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
}

@Component({
  selector: 'app-user-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="h-screen flex flex-col transition-colors duration-300"
      [class]="isDark() ? 'bg-[#020617]' : 'bg-slate-50'">

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
              <span class="text-[10px] font-medium" [class]="isDark() ? 'text-slate-500' : 'text-slate-400'">{{isConnected() ? 'Online' : 'Connecting...'}}</span>
            </div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <!-- Handoff Button -->
          <button *ngIf="!isHandoffActive()" (click)="requestHandoff()"
            class="px-4 py-2 rounded-xl text-xs font-semibold transition-colors cursor-pointer flex items-center gap-1.5"
            [class]="isDark() ? 'bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 border border-rose-500/20' : 'bg-rose-50 text-rose-600 hover:bg-rose-100 border border-rose-200'">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/></svg>
            Talk to a Human
          </button>
          <!-- Theme Toggle -->
          <button (click)="toggleTheme()" class="w-9 h-9 rounded-xl flex items-center justify-center transition-colors cursor-pointer"
            [class]="isDark() ? 'bg-slate-800 hover:bg-slate-700 text-slate-400' : 'bg-slate-100 hover:bg-slate-200 text-slate-600'">
            <svg *ngIf="isDark()" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"/></svg>
            <svg *ngIf="!isDark()" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"/></svg>
          </button>
          <!-- Logout -->
          <button (click)="logout()" class="w-9 h-9 rounded-xl flex items-center justify-center transition-colors cursor-pointer"
            [class]="isDark() ? 'bg-slate-800 hover:bg-slate-700 text-slate-400' : 'bg-slate-100 hover:bg-slate-200 text-slate-600'">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9"/></svg>
          </button>
        </div>
      </header>

      <!-- Handoff Banner -->
      <div *ngIf="isHandoffActive()" class="px-6 py-4 flex items-center gap-3 border-b animate-fade-in"
        [class]="isDark() ? 'bg-amber-500/10 border-amber-500/20' : 'bg-amber-50 border-amber-200'">
        <div class="flex-shrink-0">
          <div class="w-10 h-10 rounded-xl flex items-center justify-center" [class]="isDark() ? 'bg-amber-500/20' : 'bg-amber-100'">
            <svg class="w-5 h-5 animate-pulse" [class]="isDark() ? 'text-amber-400' : 'text-amber-600'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/></svg>
          </div>
        </div>
        <div>
          <p class="text-sm font-semibold" [class]="isDark() ? 'text-amber-300' : 'text-amber-800'">
            {{agentName() ? agentName() + ' has joined the conversation' : 'Transferring you to an I-Way specialist...'}}
          </p>
          <p class="text-xs mt-0.5" [class]="isDark() ? 'text-amber-400/70' : 'text-amber-600'">
            {{agentName() ? 'You are now chatting with a live agent.' : 'Please hold — your conversation history has been shared with our team.'}}
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
            [class]="isDark() ? 'text-white' : 'text-slate-900'">Welcome to I-Way AI Support</h2>
          <p class="text-sm max-w-sm" [class]="isDark() ? 'text-slate-500' : 'text-slate-500'">
            Ask about coverage, claims, reimbursements, or any insurance question. Our AI assistant is ready to help.
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
                : (isDark() ? 'bg-indigo-500/10' : 'bg-indigo-50')">
              <svg *ngIf="msg.role === 'assistant'" class="w-3.5 h-3.5" [class]="isDark() ? 'text-indigo-400' : 'text-indigo-500'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/></svg>
              <svg *ngIf="msg.role === 'agent'" class="w-3.5 h-3.5" [class]="isDark() ? 'text-amber-400' : 'text-amber-600'" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/></svg>
            </div>
            <div class="max-w-[75%] px-4 py-3 rounded-2xl rounded-bl-md text-sm"
              [class]="isDark() ? 'bg-[#0F172A] border border-slate-800 text-slate-300' : 'bg-white border border-slate-200 text-slate-700 shadow-sm'">
              {{msg.content}}<span *ngIf="msg.isStreaming" class="inline-block w-1.5 h-4 ml-0.5 rounded-sm animate-pulse" [class]="isDark() ? 'bg-indigo-400' : 'bg-indigo-500'"></span>
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
            <div class="flex gap-1">
              <span class="w-2 h-2 rounded-full animate-bounce" [class]="isDark() ? 'bg-indigo-400' : 'bg-indigo-500'" style="animation-delay: 0ms"></span>
              <span class="w-2 h-2 rounded-full animate-bounce" [class]="isDark() ? 'bg-indigo-400' : 'bg-indigo-500'" style="animation-delay: 150ms"></span>
              <span class="w-2 h-2 rounded-full animate-bounce" [class]="isDark() ? 'bg-indigo-400' : 'bg-indigo-500'" style="animation-delay: 300ms"></span>
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
              [placeholder]="inputDisabled() ? 'Waiting for agent...' : 'Type your message...'"
              [disabled]="inputDisabled()"
              class="w-full px-4 py-3 rounded-xl text-sm transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500/50 resize-none disabled:opacity-50"
              [class]="isDark() ? 'bg-slate-800/50 border border-slate-700 text-white placeholder-slate-500' : 'bg-slate-50 border border-slate-200 text-slate-900 placeholder-slate-400'"
              (keydown.enter)="$any($event).shiftKey ? null : onEnter($event)"></textarea>
          </div>
          <button type="submit" [disabled]="!newMessage.trim() || inputDisabled()"
            class="w-11 h-11 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 rounded-xl flex items-center justify-center text-white transition-all cursor-pointer disabled:cursor-not-allowed flex-shrink-0">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"/></svg>
          </button>
        </form>
      </div>
    </div>
  `
})
export class UserChatComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('messageContainer') private messageContainer!: ElementRef;

  messages = signal<ChatMessage[]>([]);
  newMessage = '';
  isConnected = signal(false);
  isThinking = signal(false);
  isHandoffActive = signal(false);
  agentName = signal('');
  inputDisabled = signal(false);

  private sessionId = '';
  private socket$: WebSocketSubject<any> | null = null;
  private streamingContent = '';

  quickQuestions = [
    'Plafond soins dentaires ?',
    'Delai de remboursement ?',
    'Prime de naissance ?',
    'Numero urgences ?',
  ];

  constructor(
    private authService: AuthService,
    private themeService: ThemeService,
    private http: HttpClient,
    private router: Router
  ) {}

  isDark = () => this.themeService.isDark();
  toggleTheme = () => this.themeService.toggleTheme();

  ngOnInit(): void {
    this.createSession();
  }

  ngAfterViewChecked(): void {
    this.scrollToBottom();
  }

  private createSession(): void {
    this.http.post<{session_id: string}>(`${environment.apiUrl}/api/v1/sessions/create`, {}).subscribe({
      next: (res) => {
        this.sessionId = res.session_id;
        this.connectWebSocket();
      },
      error: (err) => console.error('Failed to create session:', err)
    });
  }

  private connectWebSocket(): void {
    const wsUrl = `${environment.wsUrl.replace('/events', '')}/chat/${this.sessionId}`;
    this.socket$ = webSocket({ url: wsUrl, deserializer: (e) => JSON.parse(e.data) });

    this.socket$.subscribe({
      next: (msg) => this.handleWsMessage(msg),
      error: (err) => { console.error('WS error:', err); this.isConnected.set(false); },
      complete: () => this.isConnected.set(false),
    });

    // Identify as user
    this.socket$!.next({ type: 'user_connect' });
  }

  private handleWsMessage(msg: any): void {
    switch (msg.type) {
      case 'connected':
        this.isConnected.set(true);
        break;
      case 'history':
        if (msg.messages?.length) {
          this.messages.set(msg.messages.map((m: any) => ({ role: m.role, content: m.content, timestamp: m.timestamp })));
        }
        break;
      case 'thinking':
        this.isThinking.set(true);
        break;
      case 'ai_token':
        this.isThinking.set(false);
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
          this.messages.set([...updated.slice(0, -1), { ...lastMsg, isStreaming: false }]);
        }
        this.streamingContent = '';
        break;
      case 'handoff_started':
        this.isHandoffActive.set(true);
        this.isThinking.set(false);
        this.inputDisabled.set(true);
        this.messages.update(m => [...m, { role: 'system', content: msg.reason || 'Transferring to specialist...' }]);
        break;
      case 'agent_joined':
        this.agentName.set(msg.agent_name || 'Agent');
        this.inputDisabled.set(false); // Re-enable input for agent chat
        this.messages.update(m => [...m, { role: 'system', content: `${msg.agent_name} has joined the conversation.` }]);
        break;
      case 'agent_message':
        this.messages.update(m => [...m, { role: 'agent', content: msg.content, timestamp: msg.timestamp }]);
        break;
      case 'session_resolved':
        this.messages.update(m => [...m, { role: 'system', content: 'Session resolved. Thank you for contacting I-Way.' }]);
        this.inputDisabled.set(true);
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

  trackByIdx(index: number): number { return index; }

  private scrollToBottom(): void {
    try {
      this.messageContainer.nativeElement.scrollTop = this.messageContainer.nativeElement.scrollHeight;
    } catch {}
  }

  ngOnDestroy(): void {
    this.socket$?.complete();
  }
}
