import { Component, signal, ElementRef, ViewChild, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

interface ChatMessage {
  id: string;
  role: 'user' | 'rag' | 'ai' | 'system';
  content: string;
  timestamp: string;
  processor?: 'RAG' | 'AI Model' | 'Failed – Human Pending';
  confidence?: number;
  sources?: string[];
}

interface ConversationThread {
  id: string;
  userId: string;
  status: 'active' | 'resolved' | 'escalated';
  lastMessage: string;
  time: string;
  unread: number;
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="h-[calc(100vh-12rem)] flex gap-6">

      <!-- Conversation List -->
      <div class="w-72 flex-shrink-0 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
        <div class="p-4 border-b border-slate-100">
          <h2 class="font-bold text-slate-800 text-base mb-3">Live Conversations</h2>
          <div class="relative">
            <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0"/></svg>
            <input placeholder="Search..." class="pl-9 pr-3 py-2 text-xs border border-slate-200 rounded-lg w-full focus:outline-none focus:ring-2 focus:ring-indigo-300 transition"/>
          </div>
        </div>
        <div class="flex-1 overflow-y-auto divide-y divide-slate-50">
          <div *ngFor="let thread of threads" (click)="activeThread.set(thread)"
            [class]="'p-4 cursor-pointer transition-all ' + (activeThread()?.id === thread.id ? 'bg-indigo-50' : 'hover:bg-slate-50')">
            <div class="flex items-start justify-between mb-1">
              <span class="font-semibold text-slate-800 text-sm truncate">{{thread.userId}}</span>
              <span class="text-xs text-slate-400 flex-shrink-0 ml-2">{{thread.time}}</span>
            </div>
            <div class="text-xs text-slate-500 truncate mb-2">{{thread.lastMessage}}</div>
            <div class="flex items-center gap-2">
              <span [class]="getThreadStatusClass(thread.status)" class="text-xs px-2 py-0.5 rounded-full font-medium">{{thread.status}}</span>
              <span *ngIf="thread.unread" class="ml-auto w-5 h-5 bg-indigo-500 text-white text-xs rounded-full flex items-center justify-center font-bold">{{thread.unread}}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Chat Window -->
      <div class="flex-1 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
        <!-- Chat Header -->
        <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div class="flex items-center gap-3" *ngIf="activeThread()">
            <div class="w-9 h-9 rounded-full bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center text-white text-sm font-bold">
              {{activeThread()!.userId.charAt(0).toUpperCase()}}
            </div>
            <div>
              <div class="font-semibold text-slate-800">{{activeThread()!.userId}}</div>
              <div class="text-xs text-slate-400 flex items-center gap-1">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                Active session · ticket {{activeThread()!.id}}
              </div>
            </div>
          </div>
          <div *ngIf="!activeThread()" class="text-slate-400 text-sm">Select a conversation</div>
          <div class="flex gap-2">
            <button class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-amber-100 text-amber-700 hover:bg-amber-200 transition">Escalate</button>
            <button class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-100 text-emerald-700 hover:bg-emerald-200 transition">Resolve</button>
          </div>
        </div>

        <!-- Messages -->
        <div #messagesContainer class="flex-1 overflow-y-auto p-6 space-y-5 bg-slate-50/30">
          <ng-container *ngFor="let msg of messages">
            <!-- User message -->
            <div *ngIf="msg.role === 'user'" class="flex justify-end">
              <div class="max-w-[70%]">
                <div class="bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed shadow-sm">
                  {{msg.content}}
                </div>
                <div class="text-right text-xs text-slate-400 mt-1">{{msg.timestamp}}</div>
              </div>
            </div>

            <!-- System / AI message -->
            <div *ngIf="msg.role !== 'user' && msg.role !== 'system'" class="flex items-start gap-3">
              <div [class]="getProcessorIconClass(msg.processor)" class="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 shadow-sm">
                {{getProcessorIcon(msg.processor)}}
              </div>
              <div class="max-w-[75%]">
                <div class="flex items-center gap-2 mb-1.5">
                  <span [class]="getProcessorBadgeClass(msg.processor)" class="text-xs px-2 py-0.5 rounded-full font-semibold">{{msg.processor}}</span>
                  <span *ngIf="msg.confidence" class="text-xs text-slate-400">{{msg.confidence}}% confidence</span>
                </div>
                <div [class]="getMessageBubbleClass(msg.processor)" class="rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed shadow-sm">
                  {{msg.content}}
                </div>
                <div *ngIf="msg.sources?.length" class="mt-2 flex flex-wrap gap-1">
                  <span *ngFor="let src of msg.sources" class="inline-flex items-center gap-1 text-xs bg-white border border-slate-200 text-slate-500 px-2 py-0.5 rounded-md">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                    {{src}}
                  </span>
                </div>
                <div class="text-xs text-slate-400 mt-1">{{msg.timestamp}}</div>
              </div>
            </div>

            <!-- System event -->
            <div *ngIf="msg.role === 'system'" class="flex justify-center">
              <span class="text-xs bg-slate-100 text-slate-500 px-4 py-1.5 rounded-full font-medium">{{msg.content}}</span>
            </div>
          </ng-container>

          <!-- Typing indicator -->
          <div *ngIf="isTyping()" class="flex items-start gap-3">
            <div class="w-8 h-8 bg-emerald-100 rounded-full flex items-center justify-center text-emerald-700 text-xs font-bold">R</div>
            <div class="bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-sm flex items-center gap-1.5">
              <span class="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
              <span class="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style="animation-delay: 150ms"></span>
              <span class="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style="animation-delay: 300ms"></span>
            </div>
          </div>
        </div>

        <!-- Input -->
        <div class="px-6 py-4 border-t border-slate-100 bg-white">
          <div class="flex gap-3 items-end">
            <div class="flex-1 relative">
              <textarea [(ngModel)]="draftMessage" (keydown.enter)="sendMessage()" rows="1"
                placeholder="Type an override message or monitor passively…"
                class="w-full resize-none border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 transition leading-relaxed pr-24"></textarea>
              <div class="absolute right-3 bottom-3 flex gap-1.5">
                <button class="p-1.5 hover:bg-slate-100 rounded-lg text-slate-400 transition" title="Attach file">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"/></svg>
                </button>
              </div>
            </div>
            <button (click)="sendMessage()" class="px-5 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold transition shadow-md shadow-indigo-200 flex items-center gap-2 flex-shrink-0">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/></svg>
              Send
            </button>
          </div>
        </div>
      </div>

      <!-- Context Panel -->
      <div class="w-64 flex-shrink-0 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
        <div class="p-4 border-b border-slate-100">
          <h3 class="font-bold text-slate-800 text-sm">Session Context</h3>
        </div>
        <div class="p-4 space-y-4 text-sm overflow-y-auto">
          <div>
            <div class="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-2">Processing Path</div>
            <div class="space-y-2">
              <div class="flex items-center gap-2 text-xs">
                <div class="w-5 h-5 rounded-full bg-emerald-500 text-white flex items-center justify-center text-xs font-bold">1</div>
                <span class="text-slate-600">Vector Search (RAG)</span>
                <span class="ml-auto text-emerald-600 font-semibold">✓</span>
              </div>
              <div class="w-0.5 h-3 bg-slate-200 ml-2.5"></div>
              <div class="flex items-center gap-2 text-xs">
                <div class="w-5 h-5 rounded-full bg-indigo-500 text-white flex items-center justify-center text-xs font-bold">2</div>
                <span class="text-slate-600">LLM Generation</span>
                <span class="ml-auto text-indigo-600 font-semibold">✓</span>
              </div>
              <div class="w-0.5 h-3 bg-slate-200 ml-2.5"></div>
              <div class="flex items-center gap-2 text-xs">
                <div class="w-5 h-5 rounded-full bg-slate-200 text-slate-400 flex items-center justify-center text-xs font-bold">3</div>
                <span class="text-slate-400">Human Review</span>
                <span class="ml-auto text-slate-300 font-semibold">–</span>
              </div>
            </div>
          </div>
          <div class="border-t border-slate-100 pt-4">
            <div class="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-2">Session Stats</div>
            <div class="space-y-2">
              <div class="flex justify-between text-xs"><span class="text-slate-500">Avg Confidence</span><span class="font-semibold text-slate-700">87%</span></div>
              <div class="flex justify-between text-xs"><span class="text-slate-500">Response Time</span><span class="font-semibold text-slate-700">1.2s</span></div>
              <div class="flex justify-between text-xs"><span class="text-slate-500">RAG Sources</span><span class="font-semibold text-slate-700">3 chunks</span></div>
              <div class="flex justify-between text-xs"><span class="text-slate-500">Tokens Used</span><span class="font-semibold text-slate-700">842</span></div>
            </div>
          </div>
          <div class="border-t border-slate-100 pt-4">
            <div class="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-2">Quick Actions</div>
            <div class="space-y-2">
              <button class="w-full text-left text-xs px-3 py-2 rounded-lg hover:bg-slate-50 border border-slate-200 text-slate-600 transition">Force RAG Retry</button>
              <button class="w-full text-left text-xs px-3 py-2 rounded-lg hover:bg-slate-50 border border-slate-200 text-slate-600 transition">Inject System Prompt</button>
              <button class="w-full text-left text-xs px-3 py-2 rounded-lg hover:bg-rose-50 border border-rose-200 text-rose-600 transition">Escalate to Agent</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  `
})
export class ChatComponent {
  @ViewChild('messagesContainer') messagesContainer!: ElementRef;
  draftMessage = '';
  isTyping = signal(false);

  threads: ConversationThread[] = [
    { id: 'TKT-0091', userId: 'user_83xa', status: 'active', lastMessage: 'How do I reset my 2FA?', time: '2m', unread: 2 },
    { id: 'TKT-0090', userId: 'user_12bc', status: 'active', lastMessage: 'Incorrect VAT calculations', time: '8m', unread: 0 },
    { id: 'TKT-0089', userId: 'user_55de', status: 'escalated', lastMessage: 'CSV import failing 500 error', time: '15m', unread: 1 },
    { id: 'TKT-0088', userId: 'user_77fg', status: 'resolved', lastMessage: 'Data migration from Salesforce', time: '23m', unread: 0 },
    { id: 'TKT-0087', userId: 'user_99hi', status: 'resolved', lastMessage: 'RBAC setup for my team', time: '31m', unread: 0 },
  ];
  activeThread = signal<ConversationThread | null>(this.threads[0]);

  messages: ChatMessage[] = [
    {
      id: '1', role: 'system', content: 'Conversation started · 2 min ago',
      timestamp: '19:07'
    },
    {
      id: '2', role: 'user', content: 'How do I reset my 2FA authenticator app without losing access to my account?',
      timestamp: '19:07'
    },
    {
      id: '3', role: 'rag', content: 'To reset your 2FA authenticator without losing access, please follow these steps:\n\n1. Log in using a backup code from your saved recovery codes.\n2. Navigate to Settings → Security → Two-Factor Authentication.\n3. Click "Reset Authenticator" and scan the new QR code with your preferred app.\n\nIf you do not have backup codes, you will need to contact support for identity verification.',
      timestamp: '19:07', processor: 'RAG', confidence: 94,
      sources: ['security-guide.md', 'faq-2fa.md', 'account-recovery.md']
    },
    {
      id: '4', role: 'user', content: 'I don\'t have my backup codes, what can I do?',
      timestamp: '19:08'
    },
    {
      id: '5', role: 'ai', content: 'If you\'ve lost both your authenticator app and backup codes, our support team can verify your identity through an alternative method. This typically involves confirming your billing address, last 4 digits of payment method, and recent login timestamps. Please use the "Contact Human Support" button below to initiate this process.',
      timestamp: '19:08', processor: 'AI Model', confidence: 71,
      sources: ['identity-verification.md']
    },
  ];

  sendMessage() {
    if (!this.draftMessage.trim()) return;

    this.messages.push({
      id: Date.now().toString(),
      role: 'user',
      content: this.draftMessage.trim(),
      timestamp: new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
    });
    this.draftMessage = '';
    this.isTyping.set(true);

    setTimeout(() => {
      this.isTyping.set(false);
      this.messages.push({
        id: (Date.now() + 1).toString(),
        role: 'rag',
        content: 'I found relevant documentation for your query. Let me retrieve the most pertinent information from our knowledge base...',
        timestamp: new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }),
        processor: 'RAG',
        confidence: 82,
        sources: ['knowledge-base/general.md']
      });
    }, 1500);
  }

  getProcessorIcon(p?: string) {
    if (p === 'RAG') return 'R';
    if (p === 'AI Model') return 'AI';
    return '!';
  }
  getProcessorIconClass(p?: string) {
    if (p === 'RAG') return 'bg-emerald-100 text-emerald-700';
    if (p === 'AI Model') return 'bg-indigo-100 text-indigo-700';
    return 'bg-rose-100 text-rose-700';
  }
  getProcessorBadgeClass(p?: string) {
    if (p === 'RAG') return 'bg-emerald-100 text-emerald-700';
    if (p === 'AI Model') return 'bg-indigo-100 text-indigo-700';
    return 'bg-rose-100 text-rose-700';
  }
  getMessageBubbleClass(p?: string) {
    if (p === 'RAG') return 'bg-white border border-emerald-100 text-slate-700';
    if (p === 'AI Model') return 'bg-white border border-indigo-100 text-slate-700';
    return 'bg-white border border-rose-100 text-slate-700';
  }
  getThreadStatusClass(status: string) {
    if (status === 'active') return 'bg-emerald-100 text-emerald-700';
    if (status === 'escalated') return 'bg-rose-100 text-rose-700';
    return 'bg-slate-100 text-slate-500';
  }
}
