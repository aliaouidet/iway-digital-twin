import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts';

interface InsightCard {
  category: string;
  count: number;
  trend: 'up' | 'down' | 'stable';
  trendPct: number;
  suggestion: string;
  priority: 'high' | 'medium' | 'low';
}

@Component({
  selector: 'app-insights',
  standalone: true,
  imports: [CommonModule, NgxEchartsDirective],
  providers: [provideEchartsCore({ echarts })],
  template: `
    <div class="space-y-8">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-3xl font-bold text-slate-800 tracking-tight">AI Insights</h1>
          <p class="text-slate-500 mt-1">Identify knowledge gaps and optimize your RAG pipeline</p>
        </div>
        <div class="flex gap-3">
          <button class="px-4 py-2.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-xl text-sm font-semibold transition shadow-sm flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
            Refresh Analysis
          </button>
          <button class="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold shadow-md shadow-indigo-200 transition">Generate Report</button>
        </div>
      </div>

      <!-- KPI Row -->
      <div class="grid grid-cols-4 gap-5">
        <div class="bg-gradient-to-br from-indigo-600 to-indigo-700 text-white rounded-2xl p-6 relative overflow-hidden shadow-lg shadow-indigo-200">
          <div class="absolute right-0 top-0 w-24 h-24 bg-white/10 rounded-full -translate-y-8 translate-x-8"></div>
          <div class="text-4xl font-extrabold tracking-tight relative">23</div>
          <div class="text-indigo-200 text-sm font-medium mt-1 relative">Knowledge Gaps Found</div>
          <div class="mt-4 text-xs text-indigo-300 relative flex items-center gap-1">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/></svg>
            +5 this week
          </div>
        </div>
        <div class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <div class="text-4xl font-extrabold text-slate-800 tracking-tight">67%</div>
          <div class="text-slate-500 text-sm font-medium mt-1">RAG Coverage Rate</div>
          <div class="mt-3 w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
            <div class="w-[67%] h-full bg-indigo-500 rounded-full"></div>
          </div>
          <div class="text-xs text-slate-400 mt-1.5">Target: 85%</div>
        </div>
        <div class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <div class="text-4xl font-extrabold text-emerald-600 tracking-tight">142</div>
          <div class="text-slate-500 text-sm font-medium mt-1">Docs Suggested for Addition</div>
          <div class="text-xs text-emerald-600 mt-3 font-medium bg-emerald-50 w-fit px-2 py-0.5 rounded-md flex items-center gap-1">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18"/></svg>
            Projected +12% coverage
          </div>
        </div>
        <div class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <div class="text-4xl font-extrabold text-amber-600 tracking-tight">1,840</div>
          <div class="text-slate-500 text-sm font-medium mt-1">Failed Queries Clustered</div>
          <div class="text-xs text-amber-600 mt-3 font-medium bg-amber-50 w-fit px-2 py-0.5 rounded-md">18 distinct clusters</div>
        </div>
      </div>

      <!-- Charts Row -->
      <div class="grid grid-cols-2 gap-6">
        <div class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <h3 class="text-base font-bold text-slate-800 mb-1">Top Fallback Query Categories</h3>
          <p class="text-xs text-slate-400 mb-5">Queries that consistently bypass RAG resolution</p>
          <div echarts [options]="fallbackBarChart" class="h-[280px]"></div>
        </div>
        <div class="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <h3 class="text-base font-bold text-slate-800 mb-1">RAG Confidence Distribution</h3>
          <p class="text-xs text-slate-400 mb-5">Similarity score spread across all queries this week</p>
          <div echarts [options]="confidenceDistChart" class="h-[280px]"></div>
        </div>
      </div>

      <!-- Actionable Suggestions -->
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 class="text-base font-bold text-slate-800">Actionable Knowledge Base Suggestions</h3>
            <p class="text-xs text-slate-400 mt-0.5">AI-generated documentation topics based on failed query clusters</p>
          </div>
          <span class="text-xs bg-amber-100 text-amber-700 font-semibold px-3 py-1 rounded-full">{{insights.length}} suggestions</span>
        </div>
        <div class="divide-y divide-slate-50">
          <div *ngFor="let insight of insights" class="px-6 py-5 hover:bg-slate-50 transition-colors">
            <div class="flex items-start gap-4">
              <div [class]="getPriorityClass(insight.priority)" class="w-2 h-2 rounded-full flex-shrink-0 mt-2"></div>
              <div class="flex-1">
                <div class="flex items-center gap-3 mb-2">
                  <span class="font-semibold text-slate-800 text-sm">{{insight.category}}</span>
                  <span [class]="getPriorityBadgeClass(insight.priority)" class="text-xs px-2 py-0.5 rounded-full font-semibold">{{insight.priority}} priority</span>
                  <span class="ml-auto text-xs text-slate-400 flex items-center gap-1">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                    {{insight.count}} matching queries
                  </span>
                </div>
                <p class="text-sm text-slate-600 leading-relaxed">{{insight.suggestion}}</p>
              </div>
              <div class="flex gap-2 flex-shrink-0">
                <button class="px-3 py-1.5 text-xs font-semibold bg-indigo-50 text-indigo-600 hover:bg-indigo-100 rounded-lg transition">Create Doc</button>
                <button class="px-3 py-1.5 text-xs font-semibold bg-slate-100 text-slate-600 hover:bg-slate-200 rounded-lg transition">Dismiss</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `
})
export class InsightsComponent {
  insights: InsightCard[] = [
    { category: 'Advanced API Authentication', count: 342, trend: 'up', trendPct: 28, suggestion: 'Create dedicated docs covering OAuth 2.0 machine-to-machine flows, API key rotation policies, and HMAC signature validation. These topics cluster in 342 failed RAG queries with similarity < 0.4.', priority: 'high' },
    { category: 'EU Data Compliance & GDPR', count: 287, trend: 'up', trendPct: 15, suggestion: 'Expand the compliance section to include bulk erasure workflows, data portability exports, and DPA templates. Users are repeatedly asking questions that fall outside current knowledge base coverage.', priority: 'high' },
    { category: 'Enterprise SSO Configuration', count: 214, trend: 'stable', trendPct: 2, suggestion: 'Add step-by-step guides for Okta, Azure AD, and Google Workspace SAML configuration. Current docs only cover basic setup but miss protocol-level troubleshooting.', priority: 'high' },
    { category: 'Webhook Error Handling', count: 178, trend: 'up', trendPct: 8, suggestion: 'Document common webhook failure modes (SSL, timeout, retry logic) with code samples in Python, Node.js and Go. 89% of webhook questions escalate beyond RAG.', priority: 'medium' },
    { category: 'CSV Import Edge Cases', count: 156, trend: 'down', trendPct: 5, suggestion: 'Expand the CSV import documentation to cover encoding issues, row limits, character escaping, and error response formats. Add an interactive validator tool reference.', priority: 'medium' },
    { category: 'White-Label DNS & CDN Setup', count: 98, trend: 'stable', trendPct: 1, suggestion: 'Create a networking guide covering custom domain setup with Cloudflare, AWS Route53, and Fastly. Include SSL certificate provisioning steps and zero-downtime switchover patterns.', priority: 'low' },
  ];

  fallbackBarChart = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(255,255,255,0.95)', borderColor: '#e2e8f0', textStyle: { color: '#1e293b' } },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '5%', containLabel: true },
    xAxis: { type: 'value', axisLabel: { color: '#94a3b8', fontSize: 11 }, splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } } },
    yAxis: {
      type: 'category',
      data: ['White-Label DNS', 'CSV Import', 'Webhook Errors', 'SSO Config', 'EU GDPR', 'API Auth'],
      axisLabel: { color: '#64748b', fontSize: 11 }
    },
    series: [{
      type: 'bar',
      data: [98, 156, 178, 214, 287, 342],
      barMaxWidth: 20,
      itemStyle: {
        borderRadius: [0, 6, 6, 0],
        color: new echarts.graphic.LinearGradient(1, 0, 0, 0, [
          { offset: 0, color: '#6366f1' },
          { offset: 1, color: '#818cf8' }
        ])
      },
      label: { show: true, position: 'right', color: '#64748b', fontSize: 11, formatter: '{c}' }
    }]
  };

  confidenceDistChart = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(255,255,255,0.95)', borderColor: '#e2e8f0', textStyle: { color: '#1e293b' } },
    grid: { left: '3%', right: '4%', bottom: '10%', top: '5%', containLabel: true },
    xAxis: {
      type: 'category',
      data: ['0-0.1', '0.1-0.2', '0.2-0.3', '0.3-0.4', '0.4-0.5', '0.5-0.6', '0.6-0.7', '0.7-0.8', '0.8-0.9', '0.9-1.0'],
      axisLabel: { color: '#94a3b8', fontSize: 10, rotate: 30 }
    },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8', fontSize: 11 }, splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } } },
    series: [{
      type: 'bar',
      data: [42, 78, 120, 180, 210, 390, 580, 920, 1840, 3100],
      barMaxWidth: 30,
      itemStyle: {
        borderRadius: [4, 4, 0, 0],
        color: (params: any) => {
          const colors = ['#fecaca','#fca5a5','#f87171','#fb923c','#fbbf24','#a3e635','#4ade80','#34d399','#10b981','#059669'];
          return colors[params.dataIndex];
        }
      }
    }]
  };

  getPriorityClass(p: string) {
    if (p === 'high') return 'bg-rose-500 shadow-sm shadow-rose-300';
    if (p === 'medium') return 'bg-amber-400';
    return 'bg-slate-300';
  }

  getPriorityBadgeClass(p: string) {
    if (p === 'high') return 'bg-rose-100 text-rose-700';
    if (p === 'medium') return 'bg-amber-100 text-amber-700';
    return 'bg-slate-100 text-slate-500';
  }
}
