import { Component, OnInit, OnDestroy, signal, computed, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { TicketService } from '../../../core/services/ticket.service';
import { LogsService } from '../../../core/services/logs.service';
import { WebSocketService } from '../../../core/services/websocket.service';
import { LogEntry } from '../../../shared/models';

@Component({
  selector: 'app-tickets',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-white tracking-tight" style="font-family: 'Figtree', sans-serif;">Tickets & Alerts</h1>
          <p class="text-slate-500 mt-1 text-sm">Monitor escalated requests and RAG processing pipeline</p>
        </div>
      </div>

      <!-- Filter Tabs -->
      <div class="flex gap-2">
        <button *ngFor="let tab of filterTabs"
          (click)="activeFilter.set(tab.value)"
          [class]="activeFilter() === tab.value
            ? 'px-4 py-2 bg-indigo-600 rounded-xl text-xs font-semibold text-white transition-all cursor-pointer shadow-sm'
            : 'px-4 py-2 bg-slate-800/50 border border-slate-700/50 rounded-xl text-xs font-semibold text-slate-400 hover:text-slate-200 hover:border-slate-600 transition-all cursor-pointer'">
          {{tab.label}} ({{tab.count()}})
        </button>
      </div>

      <!-- Loading -->
      <div *ngIf="isLoading()" class="space-y-4">
        <div *ngFor="let _ of [1,2,3]" class="bg-slate-800/50 rounded-2xl border border-slate-700/50 p-6 animate-pulse">
          <div class="flex gap-4">
            <div class="h-10 w-10 bg-slate-700 rounded-xl"></div>
            <div class="flex-1 space-y-3">
              <div class="h-4 bg-slate-700 rounded w-2/3"></div>
              <div class="h-3 bg-slate-700 rounded w-1/2"></div>
            </div>
          </div>
        </div>
      </div>

      <div *ngIf="!isLoading()" class="flex gap-6">
        <!-- Ticket List -->
        <div class="flex-1 space-y-3 max-h-[70vh] overflow-y-auto pr-2 custom-scrollbar">
          <div *ngIf="filteredTickets().length === 0" class="text-center py-12 bg-[#0F172A] rounded-2xl border border-slate-800">
            <svg class="w-12 h-12 text-slate-700 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
            <p class="text-slate-500 text-sm">No tickets matching this filter</p>
          </div>

          <div *ngFor="let ticket of filteredTickets(); let i = index"
            (click)="selectTicket(ticket)"
            [class]="selectedTicket() === ticket
              ? 'bg-[#0F172A] p-5 rounded-2xl border-2 border-indigo-500/50 cursor-pointer transition-all'
              : 'bg-[#0F172A] p-5 rounded-2xl border border-slate-800 hover:border-slate-600 cursor-pointer transition-all'">
            <div class="flex items-start gap-4">
              <div [class]="getStatusIconClass(ticket.outcome)">
                <svg *ngIf="ticket.outcome === 'RAG_RESOLVED'" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                <svg *ngIf="ticket.outcome === 'AI_FALLBACK'" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3"/></svg>
                <svg *ngIf="ticket.outcome === 'HUMAN_ESCALATED'" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0"/></svg>
                <svg *ngIf="ticket.outcome === 'ERROR'" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z"/></svg>
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center justify-between mb-1">
                  <h4 class="text-sm font-semibold text-white truncate pr-4">{{ticket.query}}</h4>
                  <span [class]="getStatusBadgeClass(ticket.outcome)">{{formatOutcome(ticket.outcome)}}</span>
                </div>
                <div class="flex items-center gap-4 text-xs text-slate-500 mt-2">
                  <span class="flex items-center gap-1">
                    <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    {{ticket.timestamp}}
                  </span>
                  <span>User: {{ticket.user_id}}</span>
                  <span>Confidence: {{ticket.confidence}}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Detail Panel -->
        <div class="w-96 bg-[#0F172A] rounded-2xl border border-slate-800 p-6 max-h-[70vh] overflow-y-auto custom-scrollbar sticky top-0" *ngIf="selectedTicket()">
          <h3 class="text-base font-bold text-white mb-5" style="font-family: 'Figtree', sans-serif;">Request Details</h3>

          <div class="space-y-5">
            <div>
              <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Query</label>
              <p class="text-sm text-slate-200 mt-1 leading-relaxed">{{selectedTicket()!.query}}</p>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Model</label>
                <p class="text-sm text-slate-300 mt-1">{{selectedTicket()!.model}}</p>
              </div>
              <div>
                <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Tokens Used</label>
                <p class="text-sm text-slate-300 mt-1">{{selectedTicket()!.tokens_used}}</p>
              </div>
            </div>

            <!-- Confidence Score -->
            <div>
              <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Confidence Score</label>
              <div class="mt-2 flex items-center gap-3">
                <div class="flex-1 h-2.5 bg-slate-800 rounded-full overflow-hidden">
                  <div [style.width.%]="selectedTicket()!.confidence"
                    [class]="'h-full rounded-full transition-all duration-500 ' + getConfidenceBarColor(selectedTicket()!.confidence)"></div>
                </div>
                <span class="text-sm font-bold" [class]="getConfidenceTextColor(selectedTicket()!.confidence)">
                  {{selectedTicket()!.confidence}}%
                </span>
              </div>
            </div>

            <!-- Similarity Score -->
            <div>
              <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Top Similarity Score</label>
              <div class="mt-2 flex items-center gap-3">
                <div class="flex-1 h-2.5 bg-slate-800 rounded-full overflow-hidden">
                  <div [style.width.%]="selectedTicket()!.top_similarity * 100"
                    class="h-full rounded-full bg-indigo-500 transition-all duration-500"></div>
                </div>
                <span class="text-sm font-bold text-indigo-400">{{(selectedTicket()!.top_similarity * 100).toFixed(0)}}%</span>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Chunks Retrieved</label>
                <p class="text-sm text-slate-300 mt-1">{{selectedTicket()!.chunks_retrieved}}</p>
              </div>
              <div>
                <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Gen Time</label>
                <p class="text-sm text-slate-300 mt-1">{{selectedTicket()!.gen_time_ms}}ms</p>
              </div>
            </div>

            <!-- Action Buttons -->
            <div class="flex gap-3 pt-2">
              <button class="flex-1 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold transition-colors cursor-pointer flex items-center justify-center gap-1.5">
                <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182"/></svg>
                Reprocess
              </button>
              <button *ngIf="selectedTicket()!.outcome !== 'HUMAN_ESCALATED'" class="flex-1 px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded-xl text-xs font-semibold transition-colors cursor-pointer flex items-center justify-center gap-1.5">
                <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0"/></svg>
                Assign Human
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  `
})
export class TicketsComponent implements OnInit, OnDestroy {
  tickets = signal<LogEntry[]>([]);
  selectedTicket = signal<LogEntry | null>(null);
  activeFilter = signal('all');
  isLoading = signal(true);

  filterTabs: { label: string; value: string; count: () => number }[] = [];

  filteredTickets = computed(() => {
    const filter = this.activeFilter();
    const all = this.tickets();
    if (filter === 'all') return all;
    return all.filter(t => t.outcome === filter);
  });

  private subs: Subscription[] = [];

  constructor(
    private logsService: LogsService,
    private wsService: WebSocketService
  ) {}

  ngOnInit(): void {
    this.logsService.getLogs({ page_size: 50 }).subscribe({
      next: (data) => {
        this.tickets.set(data.items);
        this.buildFilterTabs();
        this.isLoading.set(false);
        if (data.items.length > 0) {
          this.selectedTicket.set(data.items[0]);
        }
      },
      error: () => this.isLoading.set(false)
    });

    // Real-time: new pipeline traces
    this.subs.push(
      this.wsService.getTraceUpdates().subscribe(trace => {
        if (trace && trace.query) {
          const newEntry: LogEntry = {
            id: crypto.randomUUID(),
            query: trace.query || 'Unknown query',
            outcome: trace.outcome || 'AI_FALLBACK',
            confidence: trace.confidence || 0,
            timestamp: trace.created_at || new Date().toISOString(),
            user_id: trace.user_matricule || '',
            model: trace.model_used || 'gemini-2.5-flash',
            tokens_used: trace.tokens_used || 0,
            top_similarity: trace.top_similarity || 0,
            chunks_retrieved: trace.chunks_retrieved || 0,
            gen_time_ms: trace.latency_ms || 0,
          };
          this.tickets.update(t => [newEntry, ...t]);
          this.buildFilterTabs();
        }
      })
    );

    // Real-time: new escalations
    this.subs.push(
      this.wsService.getEscalationUpdates().subscribe(escalation => {
        if (escalation) {
          const newEntry: LogEntry = {
            id: crypto.randomUUID(),
            query: escalation.reason || 'Escalation',
            outcome: 'HUMAN_ESCALATED',
            confidence: 0,
            timestamp: escalation.created_at || new Date().toISOString(),
            user_id: escalation.user_name || '',
            model: 'langgraph_agent',
            tokens_used: 0,
            top_similarity: 0,
            chunks_retrieved: 0,
            gen_time_ms: 0,
          };
          this.tickets.update(t => [newEntry, ...t]);
          this.buildFilterTabs();
        }
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach(s => s.unsubscribe());
  }

  private buildFilterTabs(): void {
    const all = this.tickets;
    this.filterTabs = [
      { label: 'All', value: 'all', count: () => all().length },
      { label: 'RAG Resolved', value: 'RAG_RESOLVED', count: () => all().filter(t => t.outcome === 'RAG_RESOLVED').length },
      { label: 'AI Fallback', value: 'AI_FALLBACK', count: () => all().filter(t => t.outcome === 'AI_FALLBACK').length },
      { label: 'Human Escalated', value: 'HUMAN_ESCALATED', count: () => all().filter(t => t.outcome === 'HUMAN_ESCALATED').length },
      { label: 'Errors', value: 'ERROR', count: () => all().filter(t => t.outcome === 'ERROR').length },
    ];
  }

  selectTicket(ticket: LogEntry): void {
    this.selectedTicket.set(ticket);
  }

  formatOutcome(outcome: string): string {
    const map: Record<string, string> = {
      'RAG_RESOLVED': 'RAG ✓',
      'AI_FALLBACK': 'AI Fallback',
      'HUMAN_ESCALATED': 'Escalated',
      'ERROR': 'Error'
    };
    return map[outcome] || outcome;
  }

  getStatusIconClass(outcome: string): string {
    const base = 'w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ';
    const map: Record<string, string> = {
      'RAG_RESOLVED': 'bg-emerald-500/15 text-emerald-400',
      'AI_FALLBACK': 'bg-indigo-500/15 text-indigo-400',
      'HUMAN_ESCALATED': 'bg-amber-500/15 text-amber-400',
      'ERROR': 'bg-rose-500/15 text-rose-400'
    };
    return base + (map[outcome] || 'bg-slate-700 text-slate-400');
  }

  getStatusBadgeClass(outcome: string): string {
    const base = 'text-[10px] font-semibold px-2.5 py-1 rounded-lg ';
    const map: Record<string, string> = {
      'RAG_RESOLVED': 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20',
      'AI_FALLBACK': 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20',
      'HUMAN_ESCALATED': 'bg-amber-500/10 text-amber-400 border border-amber-500/20',
      'ERROR': 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
    };
    return base + (map[outcome] || '');
  }

  getConfidenceBarColor(confidence: number): string {
    if (confidence >= 80) return 'bg-emerald-500';
    if (confidence >= 50) return 'bg-amber-500';
    return 'bg-rose-500';
  }

  getConfidenceTextColor(confidence: number): string {
    if (confidence >= 80) return 'text-emerald-400';
    if (confidence >= 50) return 'text-amber-400';
    return 'text-rose-400';
  }
}
