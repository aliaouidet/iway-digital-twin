import { Component, OnInit, OnDestroy, signal, computed, ChangeDetectionStrategy, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LogsService } from '../../../core/services/logs.service';
import { LogEntry, LogFilter, PaginatedLogs } from '../../../shared/models';
import { ErrorBannerComponent } from '../../../shared/components/error-banner.component';

@Component({
  selector: 'app-logs',
  standalone: true,
  imports: [CommonModule, FormsModule, ErrorBannerComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 dark:text-white tracking-tight" style="font-family: 'Figtree', sans-serif;">Logs & Audit Trail</h1>
          <p class="text-slate-500 dark:text-slate-400 mt-1 text-sm">System interaction log with full RAG processing details</p>
        </div>
        <div class="flex gap-3">
          <button (click)="exportCSV()" class="px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-semibold text-slate-700 dark:text-slate-300 transition-colors cursor-pointer flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"/></svg>
            Export CSV
          </button>
        </div>
      </div>

      <!-- Filters Section -->
      <div class="bg-white dark:bg-[#0F172A] rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm dark:shadow-none">
        <div class="flex flex-wrap gap-4 items-end">
          <div class="flex-1 min-w-[200px]">
            <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Search</label>
            <input [(ngModel)]="searchQuery" (ngModelChange)="onFilterChange()"
              placeholder="Search queries, user IDs..."
              class="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-xl text-sm text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all shadow-inner dark:shadow-none" />
          </div>
          <div class="w-44">
            <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Outcome</label>
            <select [(ngModel)]="selectedOutcome" (ngModelChange)="onFilterChange()"
              class="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-xl text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all cursor-pointer appearance-none shadow-inner dark:shadow-none">
              <option value="">All Outcomes</option>
              <option value="RAG_RESOLVED">RAG Resolved</option>
              <option value="GRAPH_RESOLVED">Graph Resolved</option>
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
          <div>
            <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Date Range</label>
            <div class="flex items-center gap-1.5">
              <input type="date" [value]="startDate" (change)="onDateChange('start', $event)" [max]="endDate || todayStr()"
                class="px-2.5 py-2 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-xl text-[11px] text-slate-700 dark:text-slate-300 font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/40 transition-all" />
              <span class="text-slate-400 text-[10px]">to</span>
              <input type="date" [value]="endDate" (change)="onDateChange('end', $event)" [max]="todayStr()" [min]="startDate"
                class="px-2.5 py-2 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-xl text-[11px] text-slate-700 dark:text-slate-300 font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/40 transition-all" />
              <button *ngIf="startDate || endDate" (click)="clearDates()" title="Clear date range"
                class="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-400 hover:text-rose-500 transition-colors cursor-pointer text-xs">✕</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Loading Skeleton -->
      <div *ngIf="isLoading()" class="bg-white dark:bg-[#0F172A] rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm dark:shadow-none">
        <!-- Skeleton header -->
        <div class="flex gap-4 px-5 py-3 border-b border-slate-200 dark:border-slate-800">
          <div *ngFor="let w of ['w-24','w-32','w-20','w-44','w-16','w-20','w-16','w-14']" class="h-3 rounded bg-slate-200 dark:bg-slate-700/40 animate-pulse" [class]="w"></div>
        </div>
        <!-- Skeleton rows -->
        <div *ngFor="let _ of [1,2,3,4,5,6,7,8]" class="flex gap-4 px-5 py-3.5 border-b border-slate-200 dark:border-slate-800/50 items-center">
          <div class="w-24 h-2.5 rounded bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
          <div class="w-32 h-2.5 rounded bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
          <div class="w-20 h-5 rounded-full bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
          <div class="w-44 h-2.5 rounded bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
          <div class="w-16 h-2.5 rounded bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
          <div class="w-20 h-5 rounded-lg bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
          <div class="w-16 h-2.5 rounded bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
          <div class="w-14 h-2.5 rounded bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
        </div>
      </div>

      <!-- Logs Table -->
      <app-error-banner *ngIf="!isLoading() && error()"
        [message]="error()!" (retry)="loadLogs()"></app-error-banner>

      <div *ngIf="!isLoading() && !error()" class="bg-white dark:bg-[#0F172A] rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm dark:shadow-none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-transparent">
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
              <ng-container *ngFor="let log of logs(); let i = index; trackBy: trackByLog">
              <tr (click)="toggleExpand(i)"
                  class="border-b border-slate-200 dark:border-slate-800/50 hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors cursor-pointer group"
                  [ngClass]="{'bg-slate-50 dark:bg-slate-800/50': expandedRow() === i}">
                <td class="px-3 py-3.5">
                  <svg class="w-3.5 h-3.5 text-slate-500 transition-transform duration-200" [class.rotate-90]="expandedRow() === i" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.25 4.5l7.5 7.5-7.5 7.5"/></svg>
                </td>
                <td class="px-5 py-3.5 text-xs text-slate-500 font-mono whitespace-nowrap" [title]="log.timestamp | date:'medium'">{{log.timestamp | date:'dd MMM, HH:mm:ss'}}</td>
                <td class="px-5 py-3.5 text-xs text-slate-500 dark:text-slate-400">{{log.user_id}}</td>
                <td class="px-5 py-3.5 text-sm text-slate-700 dark:text-slate-200 max-w-xs truncate">{{log.query}}</td>
                <td class="px-5 py-3.5">
                  <div class="flex items-center gap-2">
                    <div class="w-16 h-1.5 bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden">
                      <div [style.width.%]="log.top_similarity * 100"
                        [class]="'h-full rounded-full ' + getSimilarityColor(log.top_similarity)"></div>
                    </div>
                    <span class="text-xs text-slate-500 dark:text-slate-400 font-mono">{{(log.top_similarity * 100).toFixed(0)}}%</span>
                  </div>
                </td>
                <td class="px-5 py-3.5 text-xs text-slate-500 dark:text-slate-400 font-mono">{{log.gen_time_ms}}ms</td>
                <td class="px-5 py-3.5">
                  <span [class]="getOutcomeBadge(log.outcome)">{{formatOutcome(log.outcome)}}</span>
                </td>
                <td class="px-5 py-3.5 text-xs text-slate-500 dark:text-slate-400 font-mono">{{log.tokens_used}}</td>
              </tr>
              <!-- Inline Pipeline Waterfall Panel -->
              <tr *ngIf="expandedRow() === i">
                <td colspan="8" class="p-0 border-b border-slate-200 dark:border-slate-800/50 bg-slate-50 dark:bg-slate-900/50">
                  <div class="px-6 py-5">
                    <div class="flex items-center gap-2 mb-4">
                      <svg class="w-4 h-4 text-indigo-500 dark:text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/></svg>
                      <h4 class="text-xs font-bold text-indigo-600 dark:text-indigo-300 uppercase tracking-wider" style="font-family: 'Figtree', sans-serif;">Pipeline Waterfall</h4>
                      <span class="text-[10px] text-slate-500 ml-auto font-mono">Total: {{log.gen_time_ms}}ms</span>
                    </div>

                    <!-- Gantt Timeline Axis -->
                    <div class="relative w-full mb-2 flex items-end ml-[104px]" style="width: calc(100% - 104px - 60px);">
                      <div class="w-full border-b border-slate-300 dark:border-slate-700 relative h-4">
                        <span class="absolute top-0 left-0 text-[9px] text-slate-400 font-mono -translate-x-1/2">0ms</span>
                        <span class="absolute top-0 right-0 text-[9px] text-slate-400 font-mono translate-x-1/2">{{log.gen_time_ms}}ms</span>
                      </div>
                    </div>

                    <!-- Waterfall Bars -->
                    <div class="space-y-3 relative">
                      <div *ngFor="let span of getSpansForLog(log); let sIdx = index" class="flex flex-col">
                        <div class="flex items-center gap-3 group cursor-pointer" (click)="toggleSpan(sIdx, $event)">
                          <span class="text-[10px] text-slate-600 dark:text-slate-400 w-56 text-right font-mono flex-shrink-0 group-hover:text-indigo-500 transition-colors">{{span.name}}</span>
                          
                          <div class="flex-1 h-6 bg-slate-200/50 dark:bg-slate-800/30 rounded-md relative overflow-hidden group-hover:bg-slate-200 dark:group-hover:bg-slate-800/80 transition-colors"
                            [title]="span.name + ' · ' + span.duration_ms + 'ms · ' + span.status + (span.isBottleneck ? ' · bottleneck' : '')">
                            <div class="h-full rounded-md flex items-center px-2 transition-all duration-500 shadow-sm relative group-hover:brightness-110"
                              [style.width.%]="span.widthPct"
                              [style.margin-left.%]="span.offsetPct"
                              [class]="span.barColor">
                              <span *ngIf="span.duration_ms" class="text-[10px] font-bold text-white/90 whitespace-nowrap z-10">{{span.duration_ms}}ms</span>
                              <!-- Bottleneck Icon -->
                              <svg *ngIf="span.isBottleneck" class="w-3 h-3 text-white/90 ml-auto z-10 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
                            </div>
                          </div>

                          <div class="w-24 flex items-center justify-end gap-1 flex-shrink-0">
                            <span *ngIf="span.isBottleneck" class="flex w-2 h-2 rounded-full bg-red-500 animate-pulse" title="Bottleneck Detected"></span>
                            <span class="text-[10px] font-medium" [class]="span.status === 'completed' ? 'text-emerald-500 dark:text-emerald-400' : span.status === 'failed' ? 'text-rose-500 dark:text-rose-400' : 'text-amber-500 dark:text-amber-400'">
                              {{span.status}}
                            </span>
                          </div>
                        </div>

                        <!-- Sub-Spans (LangGraph Nodes) -->
                        <div *ngIf="span.metadata?.sub_spans?.length > 0" class="mt-2 space-y-1 relative">
                          <!-- Connection line -->
                          <div class="absolute left-[232px] top-0 bottom-0 w-px bg-slate-200 dark:bg-slate-700"></div>
                          
                          <div *ngFor="let sub of getSubSpans(span, log)" class="flex items-center gap-3 relative z-10">
                            <span class="text-[10px] font-medium text-slate-500 dark:text-slate-400 w-56 text-right flex-shrink-0 truncate" [title]="sub.name">
                              <span class="text-slate-300 dark:text-slate-600 mr-1">↳</span> {{sub.name}}
                            </span>
                            
                            <div class="flex-1 h-4 bg-transparent relative overflow-hidden group/sub">
                              <div class="h-full rounded flex items-center transition-all duration-500 shadow-sm"
                                [style.width.%]="sub.widthPct"
                                [style.margin-left.%]="sub.offsetPct"
                                [class]="sub.barColor">
                              </div>
                            </div>
                            
                            <div class="w-24 flex items-center justify-end flex-shrink-0">
                               <span class="text-[9px] text-slate-500 font-mono">{{sub.duration_ms}}ms</span>
                            </div>
                          </div>
                        </div>

                        <!-- Payload Drawer -->
                        <div *ngIf="activeSpan() === sIdx" class="ml-[236px] mt-2 mb-2 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg p-4 shadow-lg animate-in slide-in-from-top-2 fade-in duration-200 relative overflow-hidden z-20">
                           <div class="absolute top-0 left-0 w-1 h-full" [class]="span.barColor"></div>
                           <div class="flex justify-between items-center mb-3">
                             <h5 class="text-xs font-semibold text-slate-800 dark:text-slate-200">Payload Inspection <span class="text-slate-400 font-mono text-[10px] ml-1">{{span.name}}</span></h5>
                           </div>
                           <div class="text-[11px] text-slate-600 dark:text-slate-300 font-mono bg-slate-50 dark:bg-slate-900/50 rounded p-3 overflow-x-auto max-h-48 overflow-y-auto custom-scrollbar">
                              <pre class="whitespace-pre-wrap break-words">{{ span.metadata | json }}</pre>
                           </div>
                        </div>
                      </div>
                    </div>

                    <!-- Metadata Tags -->
                    <div *ngIf="log.confidence" class="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800 flex items-center gap-4">
                      <span class="text-[10px] text-slate-500">Confidence: <span class="font-bold" [class]="log.confidence >= 0.7 ? 'text-emerald-500 dark:text-emerald-400' : log.confidence >= 0.4 ? 'text-amber-500 dark:text-amber-400' : 'text-rose-500 dark:text-rose-400'">{{(log.confidence * 100).toFixed(0)}}%</span></span>
                      <span *ngIf="log.model" class="text-[10px] text-slate-500 dark:text-slate-600">Model: <span class="text-slate-700 dark:text-slate-400">{{log.model}}</span></span>
                      <span *ngIf="log.tokens_used" class="text-[10px] text-slate-500 dark:text-slate-600">Tokens: <span class="text-fuchsia-600 dark:text-fuchsia-400 font-bold">{{log.tokens_used | number}}</span></span>
                      <span class="text-[10px] text-slate-500 dark:text-slate-600">Trace: <span class="text-slate-700 dark:text-slate-400 font-mono">{{log.id.substring(0,12) || 'n/a'}}</span></span>
                    </div>
                  </div>
                </td>
              </tr>
              </ng-container>
            </tbody>
          </table>
        </div>


        <!-- Empty state -->
        <div *ngIf="logs().length === 0" class="text-center py-14">
          <svg class="w-10 h-10 mx-auto mb-3 text-slate-300 dark:text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/></svg>
          <p class="text-sm font-semibold text-slate-500 dark:text-slate-400">No pipeline traces yet</p>
          <p class="text-xs text-slate-400 dark:text-slate-600 mt-1">Traces appear here as soon as users chat with the assistant.</p>
        </div>

        <div class="px-5 py-4 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <span class="text-xs text-slate-500">Showing {{logs().length}} of {{totalLogs()}} entries</span>
          <div class="flex gap-1.5">
            <button (click)="goToPage(currentPage() - 1)" [disabled]="currentPage() <= 1"
              class="px-3 py-1.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 dark:disabled:opacity-30 disabled:cursor-not-allowed border border-slate-200 dark:border-slate-700 rounded-lg text-xs text-slate-700 dark:text-slate-400 transition-colors cursor-pointer">
              Prev
            </button>
            <span class="px-3 py-1.5 text-xs text-slate-600 dark:text-slate-400">Page {{currentPage()}} / {{totalPages()}}</span>
            <button (click)="goToPage(currentPage() + 1)" [disabled]="currentPage() >= totalPages()"
              class="px-3 py-1.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 dark:disabled:opacity-30 disabled:cursor-not-allowed border border-slate-200 dark:border-slate-700 rounded-lg text-xs text-slate-700 dark:text-slate-400 transition-colors cursor-pointer">
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  `
})
export class LogsComponent implements OnInit, OnDestroy {
  logs = signal<LogEntry[]>([]);
  isLoading = signal(true);
  error = signal<string | null>(null);
  currentPage = signal(1);
  totalPages = signal(1);
  totalLogs = signal(0);
  
  // Interactive Waterfall State
  expandedRow = signal<number | null>(null);
  activeSpan = signal<number | null>(null);
  expandedLog = computed(() => {
    const idx = this.expandedRow();
    return idx !== null ? this.logs()[idx] ?? null : null;
  });

  searchQuery = '';
  selectedOutcome = '';
  minSimilarity = 0;

  // Date-range filter (yyyy-MM-dd, optional)
  startDate = '';
  endDate = '';

  private filterTimer: any;
  private destroyRef = inject(DestroyRef);
  private route = inject(ActivatedRoute);
  private static readonly FILTER_KEY = 'iway_logs_filters';

  constructor(private logsService: LogsService) {}

  ngOnInit(): void {
    this.restoreFilters();
    // A dashboard drill-down (?outcome=RAG_RESOLVED) wins over the saved filter.
    const qpOutcome = this.route.snapshot.queryParamMap.get('outcome');
    if (qpOutcome) this.selectedOutcome = qpOutcome;
    this.loadLogs();
  }

  todayStr(): string { return new Date().toISOString().split('T')[0]; }

  onDateChange(type: 'start' | 'end', event: Event): void {
    const v = (event.target as HTMLInputElement).value;
    if (type === 'start') this.startDate = v; else this.endDate = v;
    this.currentPage.set(1);
    this.loadLogs();
  }

  clearDates(): void {
    this.startDate = '';
    this.endDate = '';
    this.currentPage.set(1);
    this.loadLogs();
  }

  ngOnDestroy(): void {
    clearTimeout(this.filterTimer);
  }

  private restoreFilters(): void {
    try {
      const raw = localStorage.getItem(LogsComponent.FILTER_KEY);
      if (!raw) return;
      const f = JSON.parse(raw);
      this.searchQuery = f.search ?? '';
      this.selectedOutcome = f.outcome ?? '';
      this.minSimilarity = f.minSimilarity ?? 0;
    } catch { /* ignore corrupt prefs */ }
  }

  private persistFilters(): void {
    try {
      localStorage.setItem(LogsComponent.FILTER_KEY, JSON.stringify({
        search: this.searchQuery, outcome: this.selectedOutcome, minSimilarity: this.minSimilarity,
      }));
    } catch { /* storage full / disabled — non-fatal */ }
  }

  trackByLog = (_: number, log: LogEntry) => log.otel_trace_id ?? log.timestamp;

  toggleExpand(index: number): void {
    if (this.expandedRow() === index) {
      this.expandedRow.set(null);
      this.activeSpan.set(null);
    } else {
      this.expandedRow.set(index);
      this.activeSpan.set(null);
    }
  }

  toggleSpan(spanIdx: number, event: MouseEvent): void {
    event.stopPropagation();
    this.activeSpan.set(this.activeSpan() === spanIdx ? null : spanIdx);
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
      const totalMs = Math.max(spans.reduce((sum: number, s: any) => sum + (s.duration_ms || 0), 0), log.gen_time_ms || 1);
      let offset = 0;
      return spans.map((s: any) => {
        const isBottleneck = (s.duration_ms || 0) / totalMs > 0.60;
        const span = {
          name: s.name,
          duration_ms: s.duration_ms,
          status: s.status,
          widthPct: Math.max((s.duration_ms || 0) / totalMs * 100, 3),
          offsetPct: offset / totalMs * 100,
          barColor: isBottleneck ? 'bg-gradient-to-r from-orange-500 to-red-500' : this.getSpanColor(s.name),
          isBottleneck,
          metadata: s.metadata || {}
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
    
    const isLlmBottleneck = llmEval / total > 0.60;

    return [
      { name: 'RECEIVED', duration_ms: 1, status: 'completed', widthPct: 3, offsetPct: 0, barColor: 'bg-slate-600', isBottleneck: false, metadata: {} },
      { name: 'RAG_SEARCH', duration_ms: ragSearch, status: 'completed', widthPct: ragSearch / total * 100, offsetPct: 0, barColor: 'bg-gradient-to-r from-cyan-500 to-cyan-400', isBottleneck: false, metadata: {} },
      { name: 'LLM_EVAL', duration_ms: llmEval, status: 'completed', widthPct: llmEval / total * 100, offsetPct: ragSearch / total * 100, barColor: isLlmBottleneck ? 'bg-gradient-to-r from-orange-500 to-red-500' : 'bg-gradient-to-r from-indigo-500 to-violet-400', isBottleneck: isLlmBottleneck, metadata: {} },
      { name: 'RESPONSE', duration_ms: response, status: 'completed', widthPct: Math.max(response / total * 100, 5), offsetPct: (ragSearch + llmEval) / total * 100, barColor: 'bg-gradient-to-r from-emerald-500 to-emerald-400', isBottleneck: false, metadata: {} },
    ];
  }

  getSubSpans(span: any, log: any): any[] {
    if (!span.metadata || !span.metadata.sub_spans || span.metadata.sub_spans.length === 0) {
      return [];
    }
    
    // Calculate total time for the parent log to get percentages right
    let totalMs = log.gen_time_ms || 1;
    if ((log as any).spans && (log as any).spans.length > 0) {
       totalMs = Math.max((log as any).spans.reduce((sum: number, s: any) => sum + (s.duration_ms || 0), 0), totalMs);
    }

    let currentMs = 0;
    
    return span.metadata.sub_spans.map((sub: any) => {
      // Calculate true offset based on actual milliseconds so it doesn't drift out of bounds
      const offsetPct = (currentMs / totalMs) * 100 + (span.offsetPct || 0);
      
      // Give it at least 1% width so it's visible to the human eye, even if it took 0.1ms
      const widthPct = Math.max((sub.duration_ms || 0) / totalMs * 100, 1);
      
      let colorClass = 'bg-indigo-300 dark:bg-indigo-900/60 border border-indigo-400/30';
      if (sub.name.includes('tool_execution')) {
         colorClass = 'bg-teal-400 dark:bg-teal-600 border border-teal-500/50';
      } else if (sub.name.includes('decompose') || sub.name.includes('draft_response') || sub.name.includes('router')) {
         colorClass = 'bg-purple-400 dark:bg-purple-600 border border-purple-500/50';
      } else if (sub.name.includes('compliance')) {
         colorClass = 'bg-blue-400 dark:bg-blue-600 border border-blue-500/50';
      }

      const res = {
        name: sub.name,
        duration_ms: sub.duration_ms,
        widthPct,
        offsetPct: offsetPct,
        barColor: colorClass
      };
      
      currentMs += (sub.duration_ms || 0);
      return res;
    });
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
      this.persistFilters();
      this.currentPage.set(1);
      this.loadLogs();
    }, 400);
  }

  goToPage(page: number): void {
    if (page < 1 || page > this.totalPages()) return;
    this.currentPage.set(page);
    this.loadLogs();
  }

  loadLogs(): void {
    this.isLoading.set(true);
    this.error.set(null);
    const filter: LogFilter = {
      page: this.currentPage(),
      page_size: 20,
      search: this.searchQuery || undefined,
      outcome: (this.selectedOutcome as any) || undefined,
      min_similarity: this.minSimilarity > 0 ? this.minSimilarity : undefined,
      start_date: this.startDate || undefined,
      end_date: this.endDate || undefined,
    };

    this.logsService.getLogs(filter)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => {
          this.logs.set(data.items);
          this.totalPages.set(data.total_pages);
          this.totalLogs.set(data.total);
          this.isLoading.set(false);
        },
        error: () => {
          this.error.set('Failed to load logs.');
          this.isLoading.set(false);
        }
      });
  }

  formatOutcome(outcome: string): string {
    const map: Record<string, string> = {
      'RAG_RESOLVED': 'RAG',
      'GRAPH_RESOLVED': 'GraphRAG',
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
      'GRAPH_RESOLVED': 'bg-blue-500/10 text-blue-400',
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
