import { Component, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

interface LogEntry {
  id: string;
  timestamp: string;
  query: string;
  userId: string;
  topSimilarity: number;
  chunksRetrieved: number;
  genTime: number;
  tokensUsed: number;
  outcome: 'RAG_RESOLVED' | 'AI_FALLBACK' | 'HUMAN_ESCALATED' | 'ERROR';
  model: string;
}

@Component({
  selector: 'app-logs',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="space-y-6">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-3xl font-bold text-slate-800 tracking-tight">Logs & Audit</h1>
          <p class="text-slate-500 mt-1">Deep-dive into every system interaction and RAG pipeline event</p>
        </div>
        <div class="flex gap-3">
          <button (click)="exportCSV()" class="px-4 py-2.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-xl text-sm font-semibold transition flex items-center gap-2 shadow-sm">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
            Export CSV
          </button>
          <button class="px-4 py-2.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-xl text-sm font-semibold transition flex items-center gap-2 shadow-sm">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z"/></svg>
            Advanced Filters
          </button>
        </div>
      </div>

      <!-- Filter Bar -->
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 flex flex-wrap gap-4 items-end">
        <div class="flex-1 min-w-[200px]">
          <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Search Query</label>
          <div class="relative">
            <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0"/></svg>
            <input [(ngModel)]="searchQuery" placeholder="Filter by query text…" class="pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg w-full focus:outline-none focus:ring-2 focus:ring-indigo-300 transition"/>
          </div>
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Outcome</label>
          <select [(ngModel)]="outcomeFilter" class="py-2 px-3 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300 transition bg-white">
            <option value="">All outcomes</option>
            <option value="RAG_RESOLVED">RAG Resolved</option>
            <option value="AI_FALLBACK">AI Fallback</option>
            <option value="HUMAN_ESCALATED">Human Escalated</option>
            <option value="ERROR">Error</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Min Similarity</label>
          <input type="range" [(ngModel)]="minSimilarity" min="0" max="100" class="w-32 accent-indigo-600"/>
          <div class="text-xs text-center text-slate-500 mt-1">≥ {{minSimilarity}}%</div>
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Date Range</label>
          <select class="py-2 px-3 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300 transition bg-white">
            <option>Last 24 hours</option>
            <option>Last 7 days</option>
            <option>Last 30 days</option>
            <option>Custom range</option>
          </select>
        </div>
        <button (click)="clearFilters()" class="px-4 py-2 text-sm text-slate-500 hover:text-slate-700 hover:bg-slate-50 rounded-lg transition font-medium">Clear</button>
      </div>

      <!-- Summary Stats -->
      <div class="grid grid-cols-5 gap-4">
        <div *ngFor="let s of summaryStats()" class="bg-white rounded-xl border border-slate-200 px-4 py-3 text-center">
          <div [class]="s.valueClass + ' text-2xl font-extrabold tracking-tight'">{{s.value}}</div>
          <div class="text-xs text-slate-500 mt-1 font-medium">{{s.label}}</div>
        </div>
      </div>

      <!-- Log Table -->
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="px-6 py-3 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <span class="text-sm text-slate-500"><strong class="text-slate-700">{{filteredLogs().length}}</strong> entries</span>
          <div class="flex items-center gap-2 text-xs text-slate-400">
            <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            Live · updating every 5s
          </div>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="border-b border-slate-100">
                <th class="text-left px-4 py-3 text-slate-400 font-semibold uppercase tracking-wider whitespace-nowrap">Timestamp</th>
                <th class="text-left px-4 py-3 text-slate-400 font-semibold uppercase tracking-wider">User</th>
                <th class="text-left px-4 py-3 text-slate-400 font-semibold uppercase tracking-wider">Query</th>
                <th class="text-left px-4 py-3 text-slate-400 font-semibold uppercase tracking-wider">Top Sim.</th>
                <th class="text-left px-4 py-3 text-slate-400 font-semibold uppercase tracking-wider">Chunks</th>
                <th class="text-left px-4 py-3 text-slate-400 font-semibold uppercase tracking-wider">Gen Time</th>
                <th class="text-left px-4 py-3 text-slate-400 font-semibold uppercase tracking-wider">Tokens</th>
                <th class="text-left px-4 py-3 text-slate-400 font-semibold uppercase tracking-wider">Model</th>
                <th class="text-left px-4 py-3 text-slate-400 font-semibold uppercase tracking-wider">Outcome</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-50">
              <tr *ngFor="let log of filteredLogs()" (click)="expandedLog.set(expandedLog() === log.id ? null : log.id)"
                class="hover:bg-slate-50 transition-colors cursor-pointer">
                <td class="px-4 py-3 font-mono text-slate-500 whitespace-nowrap">{{log.timestamp}}</td>
                <td class="px-4 py-3 text-slate-600 font-mono">{{log.userId}}</td>
                <td class="px-4 py-3 text-slate-700 max-w-[220px]">
                  <div class="truncate">{{log.query}}</div>
                </td>
                <td class="px-4 py-3">
                  <div class="flex items-center gap-1.5">
                    <div class="w-10 h-1 bg-slate-100 rounded-full overflow-hidden">
                      <div [style.width.%]="log.topSimilarity * 100" [class]="getSimilarityBarClass(log.topSimilarity)" class="h-full rounded-full"></div>
                    </div>
                    <span class="font-semibold" [class]="getSimilarityTextClass(log.topSimilarity)">{{log.topSimilarity.toFixed(2)}}</span>
                  </div>
                </td>
                <td class="px-4 py-3 text-center">
                  <span class="bg-slate-100 px-2 py-0.5 rounded font-mono">{{log.chunksRetrieved}}</span>
                </td>
                <td class="px-4 py-3">
                  <span [class]="log.genTime > 2000 ? 'text-rose-600 font-semibold' : 'text-slate-600'">{{log.genTime}}ms</span>
                </td>
                <td class="px-4 py-3 font-mono text-slate-500">{{log.tokensUsed.toLocaleString()}}</td>
                <td class="px-4 py-3">
                  <span class="bg-slate-100 text-slate-600 px-2 py-0.5 rounded-md font-mono text-xs">{{log.model}}</span>
                </td>
                <td class="px-4 py-3">
                  <span [class]="getOutcomeClass(log.outcome)" class="px-2 py-0.5 rounded-full font-semibold whitespace-nowrap text-xs">
                    {{getOutcomeLabel(log.outcome)}}
                  </span>
                </td>
              </tr>
              <tr *ngFor="let log of filteredLogs()" [class.hidden]="expandedLog() !== log.id">
                <td colspan="9" class="px-6 pt-0 pb-4 bg-slate-50">
                  <div class="bg-white rounded-xl border border-slate-200 p-4 text-xs space-y-2">
                    <div class="font-semibold text-slate-600 mb-2">Full Query Context — {{log.id}}</div>
                    <div class="text-slate-700 leading-relaxed">{{log.query}}</div>
                    <div class="flex gap-6 pt-2 text-slate-500">
                      <span>Similarity: <strong class="text-slate-700">{{log.topSimilarity}}</strong></span>
                      <span>Chunks: <strong class="text-slate-700">{{log.chunksRetrieved}}</strong></span>
                      <span>Generation: <strong class="text-slate-700">{{log.genTime}}ms</strong></span>
                      <span>Tokens: <strong class="text-slate-700">{{log.tokensUsed}}</strong></span>
                    </div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- Pagination -->
        <div class="px-6 py-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <span>Page 1 of 24 · {{logs.length * 24}} total entries</span>
          <div class="flex gap-1">
            <button class="px-3 py-1.5 rounded-lg hover:bg-slate-100 transition font-medium">← Prev</button>
            <button class="px-3 py-1.5 rounded-lg bg-slate-800 text-white font-medium">1</button>
            <button class="px-3 py-1.5 rounded-lg hover:bg-slate-100 transition font-medium">2</button>
            <button class="px-3 py-1.5 rounded-lg hover:bg-slate-100 transition font-medium">3</button>
            <button class="px-3 py-1.5 rounded-lg hover:bg-slate-100 transition font-medium">Next →</button>
          </div>
        </div>
      </div>
    </div>
  `
})
export class LogsComponent {
  searchQuery = '';
  outcomeFilter = '';
  minSimilarity = 0;
  expandedLog = signal<string | null>(null);

  logs: LogEntry[] = [
    { id: 'L001', timestamp: '2026-04-13 19:07:12', userId: 'user_83xa', query: 'How do I reset my 2FA without backup codes?', topSimilarity: 0.94, chunksRetrieved: 3, genTime: 820, tokensUsed: 842, outcome: 'RAG_RESOLVED', model: 'gpt-4o' },
    { id: 'L002', timestamp: '2026-04-13 19:06:55', userId: 'user_12bc', query: 'My invoice shows incorrect VAT for EU transactions', topSimilarity: 0.71, chunksRetrieved: 2, genTime: 1140, tokensUsed: 1203, outcome: 'AI_FALLBACK', model: 'gpt-4o' },
    { id: 'L003', timestamp: '2026-04-13 19:05:30', userId: 'user_55de', query: 'Bulk CSV import fails with 500 error on rows > 500', topSimilarity: 0.38, chunksRetrieved: 1, genTime: 2310, tokensUsed: 1842, outcome: 'HUMAN_ESCALATED', model: 'gpt-4o' },
    { id: 'L004', timestamp: '2026-04-13 19:04:01', userId: 'user_77fg', query: 'Migrating existing data from Salesforce to your platform', topSimilarity: 0.88, chunksRetrieved: 3, genTime: 750, tokensUsed: 921, outcome: 'RAG_RESOLVED', model: 'gpt-4o-mini' },
    { id: 'L005', timestamp: '2026-04-13 19:03:44', userId: 'user_99hi', query: 'Role-based access control for team members', topSimilarity: 0.96, chunksRetrieved: 3, genTime: 610, tokensUsed: 703, outcome: 'RAG_RESOLVED', model: 'gpt-4o-mini' },
    { id: 'L006', timestamp: '2026-04-13 19:02:18', userId: 'user_21jk', query: 'Webhook SSL handshake failing intermittently', topSimilarity: 0.62, chunksRetrieved: 2, genTime: 1560, tokensUsed: 1100, outcome: 'AI_FALLBACK', model: 'gpt-4o' },
    { id: 'L007', timestamp: '2026-04-13 19:01:05', userId: 'user_34lm', query: 'GDPR bulk data deletion compliance', topSimilarity: 0.45, chunksRetrieved: 2, genTime: 1980, tokensUsed: 1640, outcome: 'HUMAN_ESCALATED', model: 'gpt-4o' },
    { id: 'L008', timestamp: '2026-04-13 19:00:22', userId: 'user_56no', query: 'API rate limits exceeded despite plan upgrade', topSimilarity: 0.29, chunksRetrieved: 1, genTime: 3100, tokensUsed: 2102, outcome: 'ERROR', model: 'gpt-4o' },
    { id: 'L009', timestamp: '2026-04-13 18:59:10', userId: 'user_78pq', query: 'How to enable SSO with Okta for enterprise plan?', topSimilarity: 0.91, chunksRetrieved: 3, genTime: 690, tokensUsed: 780, outcome: 'RAG_RESOLVED', model: 'gpt-4o-mini' },
    { id: 'L010', timestamp: '2026-04-13 18:58:45', userId: 'user_90rs', query: 'Custom domain setup for white-labeling', topSimilarity: 0.83, chunksRetrieved: 3, genTime: 870, tokensUsed: 910, outcome: 'RAG_RESOLVED', model: 'gpt-4o-mini' },
  ];

  filteredLogs = computed(() => {
    return this.logs.filter(log => {
      const matchSearch = !this.searchQuery || log.query.toLowerCase().includes(this.searchQuery.toLowerCase()) || log.userId.toLowerCase().includes(this.searchQuery.toLowerCase());
      const matchOutcome = !this.outcomeFilter || log.outcome === this.outcomeFilter;
      const matchSimilarity = log.topSimilarity * 100 >= this.minSimilarity;
      return matchSearch && matchOutcome && matchSimilarity;
    });
  });

  summaryStats = computed(() => {
    const logs = this.filteredLogs();
    const avgSim = logs.reduce((a, l) => a + l.topSimilarity, 0) / (logs.length || 1);
    const avgTime = logs.reduce((a, l) => a + l.genTime, 0) / (logs.length || 1);
    const avgTokens = Math.round(logs.reduce((a, l) => a + l.tokensUsed, 0) / (logs.length || 1));
    return [
      { label: 'Total Entries', value: logs.length.toString(), valueClass: 'text-slate-800' },
      { label: 'Avg Similarity', value: avgSim.toFixed(2), valueClass: 'text-indigo-600' },
      { label: 'Avg Gen Time', value: Math.round(avgTime) + 'ms', valueClass: 'text-amber-600' },
      { label: 'Avg Tokens', value: avgTokens.toLocaleString(), valueClass: 'text-slate-700' },
      { label: 'Error Rate', value: (logs.filter(l => l.outcome === 'ERROR').length / (logs.length || 1) * 100).toFixed(1) + '%', valueClass: 'text-rose-600' },
    ];
  });

  clearFilters() {
    this.searchQuery = '';
    this.outcomeFilter = '';
    this.minSimilarity = 0;
  }

  exportCSV() {
    const headers = ['ID', 'Timestamp', 'User', 'Query', 'Top Similarity', 'Chunks', 'Gen Time(ms)', 'Tokens', 'Model', 'Outcome'];
    const rows = this.filteredLogs().map(l => [l.id, l.timestamp, l.userId, `"${l.query}"`, l.topSimilarity, l.chunksRetrieved, l.genTime, l.tokensUsed, l.model, l.outcome]);
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'iway-logs.csv';
    a.click();
  }

  getSimilarityBarClass(s: number) {
    if (s >= 0.8) return 'bg-emerald-500';
    if (s >= 0.6) return 'bg-amber-400';
    return 'bg-rose-500';
  }
  getSimilarityTextClass(s: number) {
    if (s >= 0.8) return 'text-emerald-600';
    if (s >= 0.6) return 'text-amber-600';
    return 'text-rose-600';
  }
  getOutcomeClass(o: string) {
    const m: Record<string, string> = {
      RAG_RESOLVED:    'bg-emerald-100 text-emerald-700',
      AI_FALLBACK:     'bg-indigo-100 text-indigo-700',
      HUMAN_ESCALATED: 'bg-amber-100 text-amber-700',
      ERROR:           'bg-rose-100 text-rose-700',
    };
    return m[o] || '';
  }
  getOutcomeLabel(o: string) {
    const m: Record<string, string> = {
      RAG_RESOLVED:    '✓ RAG',
      AI_FALLBACK:     '⚡ AI',
      HUMAN_ESCALATED: '⚠ Human',
      ERROR:           '✕ Error',
    };
    return m[o] || o;
  }
}
