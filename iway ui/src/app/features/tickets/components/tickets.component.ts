import { Component, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

export type TicketStatus = 'RAG_RESOLVED' | 'AI_HANDLED' | 'HUMAN_REQUIRED' | 'PENDING';

interface Ticket {
  id: string;
  userId: string;
  query: string;
  status: TicketStatus;
  confidenceScore: number;
  createdAt: string;
  assignedTo?: string;
  ragSources: number;
}

@Component({
  selector: 'app-tickets',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="space-y-6">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-3xl font-bold text-slate-800 tracking-tight">Tickets & Alerts</h1>
          <p class="text-slate-500 mt-1">Manage and review all AI-processed support requests</p>
        </div>
        <button class="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold shadow-md shadow-indigo-200 transition-all flex items-center gap-2">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
          New Ticket
        </button>
      </div>

      <!-- Stats bar -->
      <div class="grid grid-cols-4 gap-4">
        <div class="bg-white rounded-xl border border-slate-200 px-5 py-4 flex items-center gap-4">
          <div class="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-slate-600 font-bold text-lg">{{ totalTickets() }}</div>
          <div class="text-sm text-slate-500 font-medium">Total</div>
        </div>
        <div class="bg-emerald-50 rounded-xl border border-emerald-100 px-5 py-4 flex items-center gap-4">
          <div class="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center text-emerald-700 font-bold text-lg">{{ ragCount() }}</div>
          <div class="text-sm text-emerald-700 font-medium">RAG Resolved</div>
        </div>
        <div class="bg-indigo-50 rounded-xl border border-indigo-100 px-5 py-4 flex items-center gap-4">
          <div class="w-10 h-10 rounded-lg bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold text-lg">{{ aiCount() }}</div>
          <div class="text-sm text-indigo-700 font-medium">AI Handled</div>
        </div>
        <div class="bg-rose-50 rounded-xl border border-rose-100 px-5 py-4 flex items-center gap-4">
          <div class="w-10 h-10 rounded-lg bg-rose-100 flex items-center justify-center text-rose-700 font-bold text-lg">{{ humanCount() }}</div>
          <div class="text-sm text-rose-700 font-medium">Human Required</div>
        </div>
      </div>

      <!-- Filters & Table -->
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <!-- Toolbar -->
        <div class="px-6 py-4 border-b border-slate-100 flex items-center gap-4">
          <div class="relative flex-1 max-w-sm">
            <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0"/></svg>
            <input [(ngModel)]="searchQuery" placeholder="Search tickets..." class="pl-10 pr-4 py-2 text-sm border border-slate-200 rounded-lg w-full focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition"/>
          </div>
          <div class="flex gap-2">
            <button *ngFor="let f of statusFilters" (click)="activeFilter.set(f.key)"
              [class]="activeFilter() === f.key ? 'px-4 py-2 rounded-lg text-sm font-semibold transition-all bg-slate-800 text-white shadow' : 'px-4 py-2 rounded-lg text-sm font-semibold transition-all bg-slate-100 text-slate-600 hover:bg-slate-200'">
              {{f.label}}
            </button>
          </div>
        </div>

        <!-- Table -->
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-slate-100 bg-slate-50/50">
                <th class="text-left px-6 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">ID / User</th>
                <th class="text-left px-6 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Query</th>
                <th class="text-left px-6 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Status</th>
                <th class="text-left px-6 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Confidence</th>
                <th class="text-left px-6 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">RAG Sources</th>
                <th class="text-left px-6 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Created</th>
                <th class="text-left px-6 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-50">
              <tr *ngFor="let ticket of filteredTickets()" (click)="selectedTicket.set(ticket)"
                [class]="'transition-colors cursor-pointer ' + (selectedTicket()?.id === ticket.id ? 'bg-indigo-50/70' : 'hover:bg-slate-50')">
                <td class="px-6 py-4">
                  <div class="font-mono text-xs text-indigo-600 font-semibold">{{ticket.id}}</div>
                  <div class="text-slate-500 text-xs mt-0.5">{{ticket.userId}}</div>
                </td>
                <td class="px-6 py-4 max-w-[260px]">
                  <div class="text-slate-700 font-medium truncate">{{ticket.query}}</div>
                </td>
                <td class="px-6 py-4">
                  <span [class]="getStatusClass(ticket.status)" class="px-2.5 py-1 rounded-full text-xs font-semibold">
                    {{getStatusLabel(ticket.status)}}
                  </span>
                </td>
                <td class="px-6 py-4">
                  <div class="flex items-center gap-2">
                    <div class="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div [style.width.%]="ticket.confidenceScore" [class]="getConfidenceBarClass(ticket.confidenceScore)" class="h-full rounded-full transition-all"></div>
                    </div>
                    <span class="text-xs font-semibold text-slate-600">{{ticket.confidenceScore}}%</span>
                  </div>
                </td>
                <td class="px-6 py-4 text-slate-600 text-center">
                  <span class="inline-flex items-center gap-1 bg-slate-100 px-2 py-0.5 rounded text-xs font-medium">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                    {{ticket.ragSources}}
                  </span>
                </td>
                <td class="px-6 py-4 text-slate-500 text-xs whitespace-nowrap">{{ticket.createdAt}}</td>
                <td class="px-6 py-4">
                  <div class="flex gap-2">
                    <button class="p-1.5 rounded-lg hover:bg-indigo-100 text-indigo-500 transition" title="Reprocess">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                    </button>
                    <button class="p-1.5 rounded-lg hover:bg-amber-100 text-amber-500 transition" title="Assign to Human">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        <div class="px-6 py-4 border-t border-slate-100 flex items-center justify-between text-sm text-slate-500">
          <span>Showing <strong class="text-slate-700">{{filteredTickets().length}}</strong> of <strong class="text-slate-700">{{tickets.length}}</strong> tickets</span>
          <div class="flex gap-1">
            <button class="px-3 py-1.5 rounded-lg hover:bg-slate-100 transition font-medium">← Prev</button>
            <button class="px-3 py-1.5 rounded-lg bg-slate-800 text-white font-medium">1</button>
            <button class="px-3 py-1.5 rounded-lg hover:bg-slate-100 transition font-medium">2</button>
            <button class="px-3 py-1.5 rounded-lg hover:bg-slate-100 transition font-medium">3</button>
            <button class="px-3 py-1.5 rounded-lg hover:bg-slate-100 transition font-medium">Next →</button>
          </div>
        </div>
      </div>

      <!-- Detail Panel -->
      <div *ngIf="selectedTicket()" class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-6">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <span class="font-mono text-indigo-600 font-bold text-lg">{{selectedTicket()!.id}}</span>
            <span [class]="getStatusClass(selectedTicket()!.status)" class="px-2.5 py-1 rounded-full text-xs font-semibold">{{getStatusLabel(selectedTicket()!.status)}}</span>
          </div>
          <button (click)="selectedTicket.set(null)" class="p-2 hover:bg-slate-100 rounded-lg text-slate-400 transition">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="grid grid-cols-2 gap-6">
          <div>
            <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">User Query</div>
            <div class="bg-slate-50 rounded-xl p-4 text-slate-700 leading-relaxed border border-slate-100">{{selectedTicket()!.query}}</div>
          </div>
          <div>
            <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">AI Response</div>
            <div class="bg-indigo-50 rounded-xl p-4 text-indigo-900 leading-relaxed border border-indigo-100">
              Based on the retrieved knowledge base documents, the system identified the root cause and provided a resolution path. Confidence score: {{selectedTicket()!.confidenceScore}}%.
            </div>
          </div>
        </div>
        <div>
          <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">RAG Context ({{selectedTicket()!.ragSources}} sources retrieved)</div>
          <div class="space-y-2">
            <div *ngFor="let i of [1,2,3].slice(0, selectedTicket()!.ragSources)" class="flex items-start gap-3 bg-slate-50 rounded-lg p-3 border border-slate-100">
              <div class="w-6 h-6 rounded bg-indigo-100 text-indigo-600 flex items-center justify-center text-xs font-bold flex-shrink-0">{{i}}</div>
              <div>
                <div class="text-xs font-semibold text-slate-700">knowledge-base/section-{{i}}.md</div>
                <div class="text-xs text-slate-500 mt-0.5">Similarity score: {{(0.95 - i * 0.08).toFixed(2)}} • Chunk #{{i * 3 + 100}}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="flex gap-3">
          <button class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold transition shadow-md shadow-indigo-200">Reprocess Ticket</button>
          <button class="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-sm font-semibold transition shadow-md shadow-amber-200">Assign to Human</button>
          <button class="px-4 py-2 bg-white hover:bg-slate-50 text-slate-700 rounded-lg text-sm font-semibold border border-slate-200 transition">Edit AI Response</button>
        </div>
      </div>
    </div>
  `
})
export class TicketsComponent {
  searchQuery = '';
  activeFilter = signal<string>('ALL');
  selectedTicket = signal<Ticket | null>(null);

  statusFilters = [
    { key: 'ALL', label: 'All' },
    { key: 'RAG_RESOLVED', label: 'RAG' },
    { key: 'AI_HANDLED', label: 'AI' },
    { key: 'HUMAN_REQUIRED', label: 'Human' },
    { key: 'PENDING', label: 'Pending' },
  ];

  tickets: Ticket[] = [
    { id: 'TKT-0091', userId: 'user_83xa', query: 'How do I reset my 2FA authenticator app without losing access?', status: 'RAG_RESOLVED', confidenceScore: 94, createdAt: '2 min ago', ragSources: 3 },
    { id: 'TKT-0090', userId: 'user_12bc', query: 'My invoice is showing incorrect VAT calculations for EU transactions', status: 'AI_HANDLED', confidenceScore: 71, createdAt: '8 min ago', ragSources: 2 },
    { id: 'TKT-0089', userId: 'user_55de', query: 'The bulk CSV import keeps failing with a 500 error on rows > 500', status: 'HUMAN_REQUIRED', confidenceScore: 38, createdAt: '15 min ago', ragSources: 1 },
    { id: 'TKT-0088', userId: 'user_77fg', query: 'Can I migrate my existing data from Salesforce to your platform?', status: 'RAG_RESOLVED', confidenceScore: 88, createdAt: '23 min ago', ragSources: 3 },
    { id: 'TKT-0087', userId: 'user_99hi', query: 'How do I set up role-based access control for my team members?', status: 'RAG_RESOLVED', confidenceScore: 96, createdAt: '31 min ago', ragSources: 3 },
    { id: 'TKT-0086', userId: 'user_21jk', query: 'Webhook delivery is failing intermittently with SSL handshake errors', status: 'AI_HANDLED', confidenceScore: 62, createdAt: '45 min ago', ragSources: 2 },
    { id: 'TKT-0085', userId: 'user_34lm', query: 'I need to comply with GDPR data deletion requests, how do I do this in bulk?', status: 'HUMAN_REQUIRED', confidenceScore: 45, createdAt: '1 hr ago', ragSources: 2 },
    { id: 'TKT-0084', userId: 'user_56no', query: 'API rate limits are being hit even though our plan allows higher limits', status: 'PENDING', confidenceScore: 55, createdAt: '1.5 hrs ago', ragSources: 1 },
  ];

  totalTickets = computed(() => this.tickets.length);
  ragCount = computed(() => this.tickets.filter(t => t.status === 'RAG_RESOLVED').length);
  aiCount = computed(() => this.tickets.filter(t => t.status === 'AI_HANDLED').length);
  humanCount = computed(() => this.tickets.filter(t => t.status === 'HUMAN_REQUIRED').length);

  filteredTickets = computed(() => {
    let result = this.tickets;
    if (this.activeFilter() !== 'ALL') {
      result = result.filter(t => t.status === this.activeFilter());
    }
    if (this.searchQuery) {
      const q = this.searchQuery.toLowerCase();
      result = result.filter(t => t.query.toLowerCase().includes(q) || t.id.toLowerCase().includes(q) || t.userId.toLowerCase().includes(q));
    }
    return result;
  });

  getStatusClass(status: TicketStatus) {
    const map: Record<TicketStatus, string> = {
      'RAG_RESOLVED':   'bg-emerald-100 text-emerald-700',
      'AI_HANDLED':     'bg-indigo-100 text-indigo-700',
      'HUMAN_REQUIRED': 'bg-rose-100 text-rose-700',
      'PENDING':        'bg-amber-100 text-amber-700',
    };
    return map[status];
  }

  getStatusLabel(status: TicketStatus) {
    const map: Record<TicketStatus, string> = {
      'RAG_RESOLVED':   '✓ RAG Resolved',
      'AI_HANDLED':     '⚡ AI Handled',
      'HUMAN_REQUIRED': '⚠ Human Required',
      'PENDING':        '⏳ Pending',
    };
    return map[status];
  }

  getConfidenceBarClass(score: number) {
    if (score >= 80) return 'bg-emerald-500';
    if (score >= 60) return 'bg-amber-400';
    return 'bg-rose-500';
  }
}
