import { Component, OnInit, signal, computed, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LogsService } from '../../../core/services/logs.service';
import { LogEntry, LogFilter, PaginatedLogs } from '../../../shared/models';

@Component({
  selector: 'app-logs',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-white tracking-tight" style="font-family: 'Figtree', sans-serif;">Logs & Audit Trail</h1>
          <p class="text-slate-500 mt-1 text-sm">System interaction log with full RAG processing details</p>
        </div>
        <div class="flex gap-3">
          <button (click)="exportCSV()" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl text-xs font-semibold text-slate-300 transition-colors cursor-pointer flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"/></svg>
            Export CSV
          </button>
        </div>
      </div>

      <!-- Filters Section -->
      <div class="bg-[#0F172A] rounded-2xl border border-slate-800 p-5">
        <div class="flex flex-wrap gap-4 items-end">
          <div class="flex-1 min-w-[200px]">
            <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Search</label>
            <input [(ngModel)]="searchQuery" (ngModelChange)="onFilterChange()"
              placeholder="Search queries, user IDs..."
              class="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all" />
          </div>
          <div class="w-44">
            <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Outcome</label>
            <select [(ngModel)]="selectedOutcome" (ngModelChange)="onFilterChange()"
              class="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all cursor-pointer appearance-none">
              <option value="">All Outcomes</option>
              <option value="RAG_RESOLVED">RAG Resolved</option>
              <option value="AI_FALLBACK">AI Fallback</option>
              <option value="HUMAN_ESCALATED">Human Escalated</option>
              <option value="ERROR">Error</option>
            </select>
          </div>
          <div class="w-48">
            <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Min Similarity ({{minSimilarity}}%)</label>
            <input type="range" [(ngModel)]="minSimilarity" (ngModelChange)="onFilterChange()" min="0" max="100" step="5"
              class="w-full accent-indigo-500 cursor-pointer" />
          </div>
        </div>
      </div>

      <!-- Loading Skeleton -->
      <div *ngIf="isLoading()" class="bg-[#0F172A] rounded-2xl border border-slate-800 overflow-hidden">
        <!-- Skeleton header -->
        <div class="flex gap-4 px-5 py-3 border-b border-slate-800">
          <div *ngFor="let w of ['w-24','w-32','w-20','w-44','w-16','w-20','w-16','w-14']" class="h-3 rounded bg-slate-700/40 animate-pulse" [class]="w"></div>
        </div>
        <!-- Skeleton rows -->
        <div *ngFor="let _ of [1,2,3,4,5,6,7,8]" class="flex gap-4 px-5 py-3.5 border-b border-slate-800/50 items-center">
          <div class="w-24 h-2.5 rounded bg-slate-800/60 animate-pulse"></div>
          <div class="w-32 h-2.5 rounded bg-slate-800/60 animate-pulse"></div>
          <div class="w-20 h-5 rounded-full bg-slate-800/60 animate-pulse"></div>
          <div class="w-44 h-2.5 rounded bg-slate-800/60 animate-pulse"></div>
          <div class="w-16 h-2.5 rounded bg-slate-800/60 animate-pulse"></div>
          <div class="w-20 h-5 rounded-lg bg-slate-800/60 animate-pulse"></div>
          <div class="w-16 h-2.5 rounded bg-slate-800/60 animate-pulse"></div>
          <div class="w-14 h-2.5 rounded bg-slate-800/60 animate-pulse"></div>
        </div>
      </div>

      <!-- Logs Table -->
      <div *ngIf="!isLoading()" class="bg-[#0F172A] rounded-2xl border border-slate-800 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-slate-800">
                <th class="px-5 py-3.5 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider w-8"></th>
                <th class="px-5 py-3.5 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Time</th>
                <th class="px-5 py-3.5 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider">User</th>
                <th class="px-5 py-3.5 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Query</th>
                <th class="px-5 py-3.5 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Similarity</th>
                <th class="px-5 py-3.5 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Gen Time</th>
                <th class="px-5 py-3.5 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Outcome</th>
                <th class="px-5 py-3.5 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Tokens</th>
              </tr>
            </thead>
            <tbody>
              <tr *ngFor="let log of logs(); let i = index"
                  (click)="toggleExpand(i)"
                  class="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors cursor-pointer group"
                  [ngClass]="{'bg-slate-800': expandedRow() === i}">
                <td class="px-3 py-3.5">
                  <svg class="w-3.5 h-3.5 text-slate-500 transition-transform duration-200" [class.rotate-90]="expandedRow() === i" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.25 4.5l7.5 7.5-7.5 7.5"/></svg>
                </td>
                <td class="px-5 py-3.5 text-xs text-slate-500 font-mono">{{formatTime(log.timestamp)}}</td>
                <td class="px-5 py-3.5 text-xs text-slate-400">{{log.user_id}}</td>
                <td class="px-5 py-3.5 text-sm text-slate-200 max-w-xs truncate">{{log.query}}</td>
                <td class="px-5 py-3.5">
                  <div class="flex items-center gap-2">
                    <div class="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                      <div [style.width.%]="log.top_similarity * 100"
                        [class]="'h-full rounded-full ' + getSimilarityColor(log.top_similarity)"></div>
                    </div>
                    <span class="text-xs text-slate-400 font-mono">{{(log.top_similarity * 100).toFixed(0)}}%</span>
                  </div>
                </td>
                <td class="px-5 py-3.5 text-xs text-slate-400 font-mono">{{log.gen_time_ms}}ms</td>
                <td class="px-5 py-3.5">
                  <span [class]="getOutcomeBadge(log.outcome)">{{formatOutcome(log.outcome)}}</span>
                </td>
                <td class="px-5 py-3.5 text-xs text-slate-400 font-mono">{{log.tokens_used}}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pipeline Waterfall Panel (outside table) -->
        <div *ngIf="expandedLog() as log" class="px-6 py-5 bg-slate-900/50 border-t border-slate-800">
          <div class="flex items-center gap-2 mb-4">
            <svg class="w-4 h-4 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/></svg>
            <h4 class="text-xs font-bold text-indigo-300 uppercase tracking-wider" style="font-family: 'Figtree', sans-serif;">Pipeline Waterfall</h4>
            <span class="text-[10px] text-slate-500 ml-auto font-mono">Total: {{log.gen_time_ms}}ms</span>
          </div>

          <!-- Waterfall Bars -->
          <div class="space-y-2">
            <div *ngFor="let span of getSpansForLog(log)" class="flex items-center gap-3">
              <span class="text-[10px] text-slate-400 w-24 text-right font-mono flex-shrink-0">{{span.name}}</span>
              <div class="flex-1 h-5 bg-slate-800/50 rounded-md relative overflow-hidden">
                <div class="h-full rounded-md flex items-center px-2 transition-all duration-500"
                  [style.width.%]="span.widthPct"
                  [style.margin-left.%]="span.offsetPct"
                  [class]="span.barColor">
                  <span *ngIf="span.duration_ms" class="text-[9px] font-bold text-white/80 whitespace-nowrap">{{span.duration_ms}}ms</span>
                </div>
              </div>
              <span class="text-[10px] w-14 text-right flex-shrink-0" [class]="span.status === 'completed' ? 'text-emerald-400' : span.status === 'failed' ? 'text-rose-400' : 'text-amber-400'">
                {{span.status}}
              </span>
            </div>
          </div>

          <!-- Metadata Tags -->
          <div *ngIf="log.confidence" class="mt-4 pt-3 border-t border-slate-800 flex items-center gap-4">
            <span class="text-[10px] text-slate-500">Confidence: <span class="font-bold" [class]="log.confidence >= 0.7 ? 'text-emerald-400' : log.confidence >= 0.4 ? 'text-amber-400' : 'text-rose-400'">{{(log.confidence * 100).toFixed(0)}}%</span></span>
            <span *ngIf="log.model" class="text-[10px] text-slate-600">Model: <span class="text-slate-400">{{log.model}}</span></span>
            <span class="text-[10px] text-slate-600">Trace: <span class="text-slate-400 font-mono">{{log.id?.substring(0,12) || 'n/a'}}</span></span>
          </div>
        </div>


        <div class="px-5 py-4 border-t border-slate-800 flex items-center justify-between">
          <span class="text-xs text-slate-500">Showing {{logs().length}} of {{totalLogs()}} entries</span>
          <div class="flex gap-1.5">
            <button (click)="goToPage(currentPage() - 1)" [disabled]="currentPage() <= 1"
              class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed border border-slate-700 rounded-lg text-xs text-slate-400 transition-colors cursor-pointer">
              Prev
            </button>
            <span class="px-3 py-1.5 text-xs text-slate-400">Page {{currentPage()}} / {{totalPages()}}</span>
            <button (click)="goToPage(currentPage() + 1)" [disabled]="currentPage() >= totalPages()"
              class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed border border-slate-700 rounded-lg text-xs text-slate-400 transition-colors cursor-pointer">
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  `
})
export class LogsComponent implements OnInit {
  logs = signal<LogEntry[]>([]);
  isLoading = signal(true);
  currentPage = signal(1);
  totalPages = signal(1);
  totalLogs = signal(0);
  expandedRow = signal<number | null>(null);
  expandedLog = computed(() => {
    const idx = this.expandedRow();
    return idx !== null ? this.logs()[idx] ?? null : null;
  });

  searchQuery = '';
  selectedOutcome = '';
  minSimilarity = 0;

  private filterTimer: any;

  constructor(private logsService: LogsService) {}

  ngOnInit(): void {
    this.loadLogs();
  }

  toggleExpand(index: number): void {
    this.expandedRow.set(this.expandedRow() === index ? null : index);
  }

  /**
   * Generate waterfall span data for a log entry.
   * If the log has real span data (from trace), use it.
   * Otherwise, synthesize approximate spans from gen_time_ms.
   */
  getSpansForLog(log: LogEntry): any[] {
    // Try to use real spans if available
    if ((log as any).spans && (log as any).spans.length > 0) {
      const spans = (log as any).spans;
      const totalMs = spans.reduce((sum: number, s: any) => sum + (s.duration_ms || 0), 0) || 1;
      let offset = 0;
      return spans.map((s: any) => {
        const span = {
          name: s.name,
          duration_ms: s.duration_ms,
          status: s.status,
          widthPct: Math.max((s.duration_ms || 0) / totalMs * 100, 3),
          offsetPct: offset / totalMs * 100,
          barColor: this.getSpanColor(s.name),
        };
        offset += s.duration_ms || 0;
        return span;
      });
    }

    // Synthesize spans from gen_time_ms for logs without detailed trace data
    const total = log.gen_time_ms || 1;
    const ragSearch = Math.round(total * 0.25);
    const llmEval = Math.round(total * 0.55);
    const response = total - ragSearch - llmEval;

    return [
      { name: 'RECEIVED', duration_ms: 1, status: 'completed', widthPct: 3, offsetPct: 0, barColor: 'bg-slate-600' },
      { name: 'RAG_SEARCH', duration_ms: ragSearch, status: 'completed', widthPct: ragSearch / total * 100, offsetPct: 0, barColor: 'bg-gradient-to-r from-cyan-500 to-cyan-400' },
      { name: 'LLM_EVAL', duration_ms: llmEval, status: 'completed', widthPct: llmEval / total * 100, offsetPct: ragSearch / total * 100, barColor: 'bg-gradient-to-r from-indigo-500 to-violet-400' },
      { name: 'RESPONSE', duration_ms: response, status: 'completed', widthPct: Math.max(response / total * 100, 5), offsetPct: (ragSearch + llmEval) / total * 100, barColor: 'bg-gradient-to-r from-emerald-500 to-emerald-400' },
    ];
  }

  private getSpanColor(name: string): string {
    const colors: Record<string, string> = {
      'RECEIVED': 'bg-slate-600',
      'RAG_SEARCH': 'bg-gradient-to-r from-cyan-500 to-cyan-400',
      'LLM_EVAL': 'bg-gradient-to-r from-indigo-500 to-violet-400',
      'RESPONSE': 'bg-gradient-to-r from-emerald-500 to-emerald-400',
      'ESCALATED': 'bg-gradient-to-r from-amber-500 to-orange-400',
    };
    return colors[name] || 'bg-indigo-500';
  }

  onFilterChange(): void {
    clearTimeout(this.filterTimer);
    this.filterTimer = setTimeout(() => {
      this.currentPage.set(1);
      this.loadLogs();
    }, 400);
  }

  goToPage(page: number): void {
    if (page < 1 || page > this.totalPages()) return;
    this.currentPage.set(page);
    this.loadLogs();
  }

  private loadLogs(): void {
    this.isLoading.set(true);
    const filter: LogFilter = {
      page: this.currentPage(),
      page_size: 20,
      search: this.searchQuery || undefined,
      outcome: (this.selectedOutcome as any) || undefined,
      min_similarity: this.minSimilarity > 0 ? this.minSimilarity : undefined,
    };

    this.logsService.getLogs(filter).subscribe({
      next: (data) => {
        this.logs.set(data.items);
        this.totalPages.set(data.total_pages);
        this.totalLogs.set(data.total);
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false)
    });
  }

  formatTime(ts: string): string {
    return ts.split(' ').pop() || ts;
  }

  formatOutcome(outcome: string): string {
    const map: Record<string, string> = {
      'RAG_RESOLVED': 'RAG',
      'AI_FALLBACK': 'AI Fallback',
      'HUMAN_ESCALATED': 'Escalated',
      'ERROR': 'Error'
    };
    return map[outcome] || outcome;
  }

  getOutcomeBadge(outcome: string): string {
    const base = 'text-[10px] font-semibold px-2.5 py-1 rounded-lg ';
    const map: Record<string, string> = {
      'RAG_RESOLVED': 'bg-emerald-500/10 text-emerald-400',
      'AI_FALLBACK': 'bg-indigo-500/10 text-indigo-400',
      'HUMAN_ESCALATED': 'bg-amber-500/10 text-amber-400',
      'ERROR': 'bg-rose-500/10 text-rose-400'
    };
    return base + (map[outcome] || '');
  }

  getSimilarityColor(similarity: number): string {
    if (similarity >= 0.8) return 'bg-emerald-500';
    if (similarity >= 0.5) return 'bg-amber-500';
    return 'bg-rose-500';
  }

  exportCSV(): void {
    const headers = ['ID', 'Timestamp', 'User', 'Query', 'Similarity', 'Gen Time (ms)', 'Tokens', 'Outcome', 'Confidence'];
    const rows = this.logs().map(l => [
      l.id, l.timestamp, l.user_id, `"${l.query}"`,
      l.top_similarity, l.gen_time_ms, l.tokens_used, l.outcome, l.confidence
    ]);
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `iway-logs-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
