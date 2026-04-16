import { Component, OnInit, OnDestroy, signal, ViewChild, ElementRef, AfterViewChecked, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { WebSocketService, WsMessage } from '../../../core/services/websocket.service';
import { AuthService } from '../../../core/services/auth.service';
import { TicketService } from '../../../core/services/ticket.service';

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
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                Online · RAG + LLM Pipeline
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
          <div *ngIf="messages().length === 0" class="flex flex-col items-center justify-center h-full text-center">
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
        </div>

        <!-- Input Area -->
        <div class="p-4 border-t border-slate-800">
          <form (ngSubmit)="sendMessage()" class="flex gap-3 items-end">
            <div class="flex-1 relative">
              <textarea [(ngModel)]="newMessage" name="message"
                rows="1"
                placeholder="Ask about coverage, claims, reimbursements..."
                class="w-full px-4 py-3 bg-slate-800/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all resize-none"
                (keydown.enter)="$any($event).shiftKey ? null : onEnter($event)"></textarea>
            </div>
            <button type="submit" [disabled]="!newMessage.trim() || isSending()"
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
  private shouldScroll = false;
  private wsSub?: Subscription;

  quickQuestions = [
    'Plafond soins dentaires ?',
    'Delai de remboursement ?',
    'Prime de naissance ?',
    'Prise en charge urgence ?',
  ];

  constructor(
    private wsService: WebSocketService,
    private authService: AuthService,
    private ticketService: TicketService
  ) {}

  ngOnInit(): void {
    // Listen for chat messages from WebSocket
    this.wsSub = this.wsService.getMessages().subscribe(msg => {
      if (msg.type === 'CHAT_RESPONSE') {
        this.handleWsResponse(msg.payload);
      }
    });
  }

  ngAfterViewChecked(): void {
    if (this.shouldScroll) {
      this.scrollToBottom();
      this.shouldScroll = false;
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
    if (!content || this.isSending()) return;

    // Add user message
    const userMsg: ChatMsg = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      timestamp: new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
    };
    this.messages.update(msgs => [...msgs, userMsg]);
    this.newMessage = '';
    this.shouldScroll = true;
    this.isSending.set(true);

    // Send via WebSocket
    this.wsService.sendMessage({
      type: 'CHAT_QUERY',
      payload: {
        query: content,
        matricule: this.authService.getCurrentUser()?.matricule || ''
      }
    });

    // Simulate AI response (since backend chat endpoint uses the LangGraph agent)
    // In production, this would come via WebSocket CHAT_RESPONSE event
    setTimeout(() => {
      const assistantMsg: ChatMsg = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: this.getSimulatedResponse(content),
        timestamp: new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
        processor: this.getProcessor(content),
      };
      this.messages.update(msgs => [...msgs, assistantMsg]);
      this.shouldScroll = true;
      this.isSending.set(false);
    }, 1500 + Math.random() * 1500);
  }

  clearChat(): void {
    this.messages.set([]);
  }

  getProcessorBadge(processor: string): string {
    const base = 'text-[10px] font-semibold px-2 py-0.5 rounded-md ';
    if (processor === 'RAG') return base + 'bg-emerald-500/10 text-emerald-400';
    if (processor === 'AI Model') return base + 'bg-indigo-500/10 text-indigo-400';
    return base + 'bg-amber-500/10 text-amber-400';
  }

  private handleWsResponse(payload: any): void {
    const msg: ChatMsg = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: payload.content || payload.text || '',
      timestamp: new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
      processor: payload.processor || 'RAG',
    };
    this.messages.update(msgs => [...msgs, msg]);
    this.shouldScroll = true;
    this.isSending.set(false);
  }

  private getSimulatedResponse(query: string): string {
    const q = query.toLowerCase();
    if (q.includes('dentaire') || q.includes('dental')) {
      return 'Selon l\'Article 4 de la convention, le plafond annuel pour les soins dentaires est de 600 TND par beneficiaire. Les protheses dentaires sont couvertes a 70% dans la limite de ce plafond. Les soins orthodontiques pour les enfants de moins de 16 ans beneficient d\'un plafond supplementaire de 400 TND.';
    }
    if (q.includes('remboursement') || q.includes('delai')) {
      return 'Les remboursements sont traites sous 48h ouvrees pour les feuilles de soins electroniques (FSE). Les feuilles papier peuvent prendre jusqu\'a 15 jours ouvres. Les virements sont effectues sur le RIB enregistre dans votre espace.';
    }
    if (q.includes('naissance') || q.includes('prime')) {
      return 'La prime de naissance est de 300 TND par enfant, versee sur presentation de l\'acte de naissance dans un delai de 30 jours suivant la naissance. En cas de naissances multiples, la prime est versee pour chaque enfant.';
    }
    if (q.includes('urgence')) {
      return 'En cas d\'urgence, rendez-vous aux services d\'urgence les plus proches. Les frais seront pris en charge a 100% sur presentation de votre carte d\'adherent. Le numero d\'urgence I-Way est le 71 800 800.';
    }
    if (q.includes('humain') || q.includes('agent') || q.includes('parler')) {
      return 'Je transfère votre demande a un agent humain. Un ticket d\'escalation a ete cree. Position dans la file: 2. Temps d\'attente estime: 5 minutes.';
    }
    return 'Je recherche dans la base de connaissances I-Way pour repondre a votre question. D\'apres les informations disponibles, je vous recommande de consulter votre espace adherent ou de contacter notre service client au 71 800 800 pour une assistance personnalisee.';
  }

  private getProcessor(query: string): string {
    const q = query.toLowerCase();
    if (q.includes('humain') || q.includes('agent')) return 'Human Escalation';
    if (q.includes('dentaire') || q.includes('remboursement') || q.includes('naissance') || q.includes('urgence') || q.includes('plafond')) return 'RAG';
    return 'AI Model';
  }

  private scrollToBottom(): void {
    try {
      this.messagesContainer.nativeElement.scrollTop = this.messagesContainer.nativeElement.scrollHeight;
    } catch {}
  }

  ngOnDestroy(): void {
    this.wsSub?.unsubscribe();
  }
}
