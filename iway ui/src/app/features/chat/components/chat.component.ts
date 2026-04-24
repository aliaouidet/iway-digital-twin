import { Component, OnInit, OnDestroy, signal, ViewChild, ElementRef, AfterViewChecked, ChangeDetectionStrategy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Subscription } from 'rxjs';
import { ChatService } from '../services/chat.service';
import { AuthService } from '../../../core/services/auth.service';
import { TicketService } from '../../../core/services/ticket.service';
import { environment } from '../../../../environments/environment';

interface ChatMsg {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  processor?: string;
  isStreaming?: boolean;
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex h-[calc(100vh-8rem)] gap-6">
      <!-- Chat Area -->
      <div class="flex-1 flex flex-col bg-[#0F172A] rounded-2xl border border-slate-800 overflow-hidden">
        <!-- Chat Header -->
        <div class="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center">
              <svg class="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z"/></svg>
            </div>
            <div>
              <h3 class="text-sm font-bold text-white">I-Sante AI Assistant</h3>
              <div class="flex items-center gap-1.5 text-xs text-slate-500">
                <span class="w-1.5 h-1.5 rounded-full" [class]="isSessionReady() ? 'bg-emerald-500' : 'bg-amber-500 animate-pulse'"></span>
                {{isSessionReady() ? 'Online · RAG + LLM Pipeline' : 'Connecting...'}}
              </div>
            </div>
          </div>
          <button (click)="clearChat()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs text-slate-400 hover:text-white transition-colors cursor-pointer">
            Clear
          </button>
        </div>

        <!-- Messages -->
        <div #messagesContainer class="flex-1 overflow-y-auto px-6 py-6 space-y-6 custom-scrollbar">
          <!-- Welcome State -->
          <div *ngIf="messages().length === 0 && !isThinking()" class="flex flex-col items-center justify-center h-full text-center">
            <div class="w-16 h-16 bg-indigo-500/10 rounded-2xl flex items-center justify-center mb-5">
              <svg class="w-8 h-8 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/></svg>
            </div>
            <h3 class="text-lg font-bold text-white mb-2" style="font-family: 'Figtree', sans-serif;">Ask I-Sante anything</h3>
            <p class="text-sm text-slate-500 max-w-md">Questions about insurance coverage, reimbursements, medical claims, and more — powered by RAG + AI.</p>
            <div class="grid grid-cols-2 gap-2 mt-6 max-w-sm">
              <button *ngFor="let q of quickQuestions" (click)="sendQuickQuestion(q)"
                class="px-3 py-2 bg-slate-800/60 border border-slate-700/50 hover:border-indigo-500/50 rounded-xl text-xs text-slate-400 hover:text-white transition-all cursor-pointer text-left">
                {{q}}
              </button>
            </div>
          </div>

          <!-- Connection Error State -->
          <div *ngIf="connectionError()" class="flex flex-col items-center justify-center h-full text-center">
            <div class="w-16 h-16 bg-red-500/10 rounded-2xl flex items-center justify-center mb-5">
              <svg class="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/></svg>
            </div>
            <h3 class="text-lg font-bold text-white mb-2">Connection Error</h3>
            <p class="text-sm text-red-400/80 max-w-md">{{connectionError()}}</p>
            <button (click)="retryConnection()" class="mt-4 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm text-white transition-colors cursor-pointer">
              Retry
            </button>
          </div>

          <!-- Message List -->
          <div *ngFor="let msg of messages()" class="flex" [class]="msg.role === 'user' ? 'justify-end' : 'justify-start'">
            <div class="max-w-[70%] group">
              <!-- User Message -->
              <div *ngIf="msg.role === 'user'" class="bg-indigo-600 px-5 py-3 rounded-2xl rounded-br-md">
                <p class="text-sm text-white leading-relaxed">{{msg.content}}</p>
              </div>
              <!-- Assistant Message -->
              <div *ngIf="msg.role === 'assistant'" class="flex items-start gap-3">
                <div class="w-7 h-7 rounded-lg bg-indigo-500/15 flex items-center justify-center flex-shrink-0 mt-1">
                  <svg class="w-3.5 h-3.5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25"/></svg>
                </div>
                <div class="bg-slate-800/60 px-5 py-3 rounded-2xl rounded-bl-md border border-slate-700/50">
                  <p class="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap">{{msg.content}}<span *ngIf="msg.isStreaming" class="inline-block w-1.5 h-4 bg-indigo-400 animate-pulse ml-0.5 align-text-bottom rounded-sm"></span></p>
                  <div *ngIf="msg.processor" class="mt-2 flex items-center gap-2">
                    <span [class]="getProcessorBadge(msg.processor)">{{msg.processor}}</span>
                  </div>
                </div>
              </div>
              <div class="text-[10px] text-slate-600 mt-1" [class]="msg.role === 'user' ? 'text-right' : 'text-left pl-10'">{{msg.timestamp}}</div>
            </div>
          </div>

          <!-- Streaming Message -->
          <div *ngIf="currentStreamingMessage()" class="flex justify-start">
            <div class="max-w-[70%] group">
              <div class="flex items-start gap-3">
                <div class="w-7 h-7 rounded-lg bg-indigo-500/15 flex items-center justify-center flex-shrink-0 mt-1">
                  <svg class="w-3.5 h-3.5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25"/></svg>
                </div>
                <div class="bg-slate-800/60 px-5 py-3 rounded-2xl rounded-bl-md border border-slate-700/50">
                  <p class="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap">{{currentStreamingMessage()}}<span class="inline-block w-1.5 h-4 bg-indigo-400 animate-pulse ml-0.5 align-text-bottom rounded-sm"></span></p>
                </div>
              </div>
            </div>
          </div>

          <!-- Thinking State -->
          <div *ngIf="isThinking()" class="flex justify-start">
            <div class="flex items-center gap-3 bg-slate-800/40 px-4 py-2.5 rounded-full border border-slate-700/50">
               <svg class="w-4 h-4 text-indigo-400 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
               <span class="text-xs text-slate-400">{{thinkingStatus() || 'Processing...'}}</span>
            </div>
          </div>

          <!-- Handoff Banner -->
          <div *ngIf="isHandoffTriggered()" class="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4 flex items-start gap-3 mt-4">
            <svg class="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
            <div>
              <h4 class="text-sm font-semibold text-amber-400">Escalating to Human Agent</h4>
              <p class="text-xs text-amber-500/80 mt-1">{{handoffReason() || 'Transferring your chat to the next available agent.'}}</p>
            </div>
          </div>
        </div>

        <!-- Input Area -->

        <div class="p-4 border-t border-slate-800">
          <form (ngSubmit)="sendMessage()" class="flex gap-3 items-end">
            <div class="flex-1 relative">
              <textarea [(ngModel)]="newMessage" name="message"
                rows="1"
                placeholder="Ask about coverage, claims, reimbursements..."
                class="w-full px-4 py-3 bg-slate-800/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all resize-none"
                [disabled]="!isSessionReady() || isHandoffTriggered()"
                (keydown.enter)="$any($event).shiftKey ? null : onEnter($event)"></textarea>
            </div>
            <button type="submit" [disabled]="!newMessage.trim() || isSending() || !isSessionReady()"
              class="w-11 h-11 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-600 rounded-xl flex items-center justify-center text-white transition-all cursor-pointer disabled:cursor-not-allowed flex-shrink-0">
              <svg *ngIf="!isSending()" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"/></svg>
              <svg *ngIf="isSending()" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
            </button>
          </form>
        </div>
      </div>

      <!-- Context Panel -->
      <div class="w-72 space-y-4 hidden xl:block">
        <div class="bg-[#0F172A] rounded-2xl border border-slate-800 p-5">
          <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Session Info</h3>
          <div class="space-y-3">
            <div class="flex justify-between text-sm"><span class="text-slate-500">Messages</span><span class="text-white font-semibold">{{messages().length}}</span></div>
            <div class="flex justify-between text-sm"><span class="text-slate-500">Pipeline</span><span class="text-emerald-400 font-semibold text-xs">RAG → LLM → Human</span></div>
            <div class="flex justify-between text-sm"><span class="text-slate-500">Model</span><span class="text-slate-300 font-semibold text-xs">Gemini 2.5 Flash</span></div>
          </div>
        </div>
        <div class="bg-[#0F172A] rounded-2xl border border-slate-800 p-5">
          <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Processing Pipeline</h3>
          <div class="space-y-3">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg bg-emerald-500/15 flex items-center justify-center"><span class="text-emerald-400 text-xs font-bold">1</span></div>
              <div>
                <div class="text-xs font-semibold text-white">RAG Search</div>
                <div class="text-[10px] text-slate-500">FAISS vector similarity</div>
              </div>
            </div>
            <div class="w-px h-3 bg-slate-700 ml-4"></div>
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg bg-indigo-500/15 flex items-center justify-center"><span class="text-indigo-400 text-xs font-bold">2</span></div>
              <div>
                <div class="text-xs font-semibold text-white">LLM Generation</div>
                <div class="text-[10px] text-slate-500">Gemini / Qwen fallback</div>
              </div>
            </div>
            <div class="w-px h-3 bg-slate-700 ml-4"></div>
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg bg-amber-500/15 flex items-center justify-center"><span class="text-amber-400 text-xs font-bold">3</span></div>
              <div>
                <div class="text-xs font-semibold text-white">Human Escalation</div>
                <div class="text-[10px] text-slate-500">Support agent queue</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `
})
export class ChatComponent implements OnInit, OnDestroy, AfterViewChecked {

  @ViewChild('messagesContainer') private messagesContainer!: ElementRef;

  messages = signal<ChatMsg[]>([]);
  newMessage = '';
  isSending = signal(false);
  isSessionReady = signal(false);
  connectionError = signal('');

  // Streaming UI signals
  currentStreamingMessage = signal('');
  isThinking = signal(false);
  thinkingStatus = signal('');
  isHandoffTriggered = signal(false);
  handoffReason = signal('');

  // Fixed: shouldScroll is now a signal for OnPush compatibility
  private shouldScroll = signal(false);
  private wsSubs: Subscription[] = [];
  private sessionId: string | null = null;

  quickQuestions = [
    'Plafond soins dentaires ?',
    'Delai de remboursement ?',
    'Prime de naissance ?',
    'Prise en charge urgence ?',
  ];

  constructor(
    private chatService: ChatService,
    private authService: AuthService,
    private ticketService: TicketService,
    private http: HttpClient,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.initializeSession();
  }

  /**
   * Phase 1 Fix: Create session via HTTP first, then connect WebSocket.
   * This ensures the backend has a valid SESSIONS entry before the WS opens.
   */
  private initializeSession(): void {
    const token = this.authService.getToken();
    if (!token) {
      this.connectionError.set('Please log in to start chatting.');
      return;
    }

    const headers = new HttpHeaders({ Authorization: `Bearer ${token}` });

    this.http.post<{ session_id: string }>(
      `${environment.apiUrl}/api/v1/sessions/create`,
      {},
      { headers }
    ).subscribe({
      next: (response) => {
        this.sessionId = response.session_id;
        this.connectWebSocket(this.sessionId);
      },
      error: (err) => {
        console.error('[Chat] Failed to create session:', err);
        this.connectionError.set('Failed to create chat session. Please try again.');
        this.cdr.markForCheck();
      }
    });
  }

  private connectWebSocket(sessionId: string): void {
    this.chatService.connect(sessionId);

    // Listen to connection confirmation
    this.wsSubs.push(
      this.chatService.connected$.subscribe(() => {
        this.isSessionReady.set(true);
        this.connectionError.set('');
        this.cdr.markForCheck();
      })
    );

    // Listen to token streams
    this.wsSubs.push(
      this.chatService.token$.subscribe(token => {
        this.isThinking.set(false);
        this.currentStreamingMessage.update(msg => msg + token);
        this.shouldScroll.set(true);
      })
    );

    // Listen to thinking state
    this.wsSubs.push(
      this.chatService.thinking$.subscribe(state => {
        this.isThinking.set(true);
        this.thinkingStatus.set(state.status);
        this.shouldScroll.set(true);
      })
    );

    // Listen to done state
    this.wsSubs.push(
      this.chatService.done$.subscribe(state => {
        const content = this.currentStreamingMessage();
        if (content) {
          const msg: ChatMsg = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: content,
            timestamp: new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
            processor: state.source || 'AI Model',
          };
          this.messages.update(msgs => [...msgs, msg]);
          this.currentStreamingMessage.set('');
        }
        this.isThinking.set(false);
        this.isSending.set(false);
        this.shouldScroll.set(true);
      })
    );

    // Listen to handoff triggers
    this.wsSubs.push(
      this.chatService.handoff$.subscribe(state => {
        this.isHandoffTriggered.set(true);
        this.handoffReason.set(state.reason);
        this.isSending.set(false);
        this.isThinking.set(false);
        this.shouldScroll.set(true);
      })
    );

    // Listen to chat history (reconnection / initial load)
    this.wsSubs.push(
      this.chatService.history$.subscribe(history => {
        const mapped: ChatMsg[] = history.map((msg: any) => ({
           id: crypto.randomUUID(),
           role: (msg.role || (msg.type === 'human' ? 'user' : 'assistant')) as 'user' | 'assistant' | 'system',
           content: msg.content,
           timestamp: msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
           processor: msg.source || (msg.type === 'ai' ? 'AI Model' : undefined)
        }));
        this.messages.set(mapped);
        this.shouldScroll.set(true);
      })
    );

    // Listen to errors
    this.wsSubs.push(
      this.chatService.error$.subscribe(error => {
        this.connectionError.set(error);
        this.isSending.set(false);
        this.isThinking.set(false);
        this.cdr.markForCheck();
      })
    );
  }

  ngAfterViewChecked(): void {
    if (this.shouldScroll()) {
      this.scrollToBottom();
      this.shouldScroll.set(false);
    }
  }

  sendQuickQuestion(q: string): void {
    this.newMessage = q;
    this.sendMessage();
  }

  onEnter(event: Event): void {
    event.preventDefault();
    this.sendMessage();
  }

  sendMessage(): void {
    const content = this.newMessage.trim();
    if (!content || this.isSending() || this.isHandoffTriggered() || !this.isSessionReady()) return;

    // Add user message locally
    const userMsg: ChatMsg = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      timestamp: new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
    };
    this.messages.update(msgs => [...msgs, userMsg]);
    this.newMessage = '';
    this.shouldScroll.set(true);
    this.isSending.set(true);

    // Clear previous stream states
    this.currentStreamingMessage.set('');
    this.isThinking.set(true);
    this.thinkingStatus.set('Envoi de la demande...');

    // Send over ChatService WebSocket
    this.chatService.sendMessage(content);
  }

  clearChat(): void {
    this.messages.set([]);
    this.isHandoffTriggered.set(false);
    this.isSessionReady.set(false);
    this.connectionError.set('');
    // Disconnect old session and create a new one
    this.chatService.disconnect();
    this.wsSubs.forEach(s => s.unsubscribe());
    this.wsSubs = [];
    this.initializeSession();
  }

  retryConnection(): void {
    this.connectionError.set('');
    this.initializeSession();
  }

  getProcessorBadge(processor: string): string {
    const base = 'text-[10px] font-semibold px-2 py-0.5 rounded-md ';
    if (processor === 'RAG') return base + 'bg-emerald-500/10 text-emerald-400';
    if (processor === 'AI Model') return base + 'bg-indigo-500/10 text-indigo-400';
    return base + 'bg-amber-500/10 text-amber-400';
  }

  private scrollToBottom(): void {
    try {
      this.messagesContainer.nativeElement.scrollTop = this.messagesContainer.nativeElement.scrollHeight;
    } catch {}
  }

  ngOnDestroy(): void {
    this.wsSubs.forEach(s => s.unsubscribe());
    this.chatService.disconnect();
  }
}
