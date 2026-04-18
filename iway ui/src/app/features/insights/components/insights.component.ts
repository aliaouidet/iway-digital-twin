import { Component, OnInit, signal, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts';
import { InsightsService } from '../../../core/services/insights.service';
import { InsightsData, InsightSuggestion } from '../../../shared/models';
import { environment } from '../../../../environments/environment';

interface KnowledgeGap {
  query: string;
  confidence: number | null;
  outcome: string;
  session_id: string;
  timestamp: string;
}

interface GapData {
  total_gaps: number;
  gaps: KnowledgeGap[];
  top_missing_topics: { topic: string; count: number }[];
}

interface CsatStats {
  total: number;
  positive: number;
  negative: number;
  csat_score: number;
  recent: any[];
}

@Component({
  selector: 'app-insights',
  standalone: true,
  imports: [CommonModule, NgxEchartsDirective],
  providers: [provideEchartsCore({ echarts })],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-white tracking-tight" style="font-family: 'Figtree', sans-serif;">AI Insights</h1>
          <p class="text-slate-500 mt-1 text-sm">Knowledge gap analysis and RAG performance intelligence</p>
        </div>
        <button (click)="refreshData()" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-xl text-xs font-semibold text-white transition-colors cursor-pointer flex items-center gap-1.5">
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182"/></svg>
          Refresh Analysis
        </button>
      </div>

      <!-- Summary Cards -->
      <div *ngIf="!isLoading() && data()" class="grid grid-cols-1 md:grid-cols-5 gap-5">
        <div class="bg-[#0F172A] p-5 rounded-2xl border border-slate-800">
          <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">Knowledge Gaps</div>
          <div class="text-2xl font-extrabold" style="color: #fb7185;">{{gapData()?.total_gaps || data()!.knowledge_gaps}}</div>
          <div class="text-xs text-slate-500 mt-1">Topics missing coverage</div>
        </div>
        <div class="bg-[#0F172A] p-5 rounded-2xl border border-slate-800">
          <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">RAG Coverage</div>
          <div class="text-2xl font-extrabold text-emerald-400">{{data()!.rag_coverage_rate}}%</div>
          <div class="text-xs text-slate-500 mt-1">Questions auto-resolved</div>
        </div>
        <div class="bg-[#0F172A] p-5 rounded-2xl border border-slate-800">
          <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">Docs Suggested</div>
          <div class="text-2xl font-extrabold text-indigo-400">{{data()!.docs_suggested}}</div>
          <div class="text-xs text-slate-500 mt-1">Articles to create</div>
        </div>
        <div class="bg-[#0F172A] p-5 rounded-2xl border border-slate-800">
          <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">Failed Clusters</div>
          <div class="text-2xl font-extrabold text-amber-400">{{data()!.failed_clusters}}</div>
          <div class="text-xs text-slate-500 mt-1">Query groups failing</div>
        </div>
        <!-- CSAT Score Card -->
        <div class="bg-[#0F172A] p-5 rounded-2xl border border-slate-800">
          <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">CSAT Score</div>
          <div class="text-2xl font-extrabold" [class]="(csatData()?.csat_score ?? 0) >= 70 ? 'text-emerald-400' : (csatData()?.csat_score ?? 0) >= 40 ? 'text-amber-400' : 'text-rose-400'">
            {{csatData()?.csat_score ?? '--'}}%
          </div>
          <div class="text-xs text-slate-500 mt-1">{{csatData()?.total || 0}} total ratings</div>
        </div>
      </div>

      <!-- Charts + Suggestions -->
      <div *ngIf="!isLoading() && data()" class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Confidence Distribution -->
        <div class="bg-[#0F172A] rounded-2xl border border-slate-800 p-6">
          <h3 class="text-sm font-bold text-white mb-5" style="font-family: 'Figtree', sans-serif;">Confidence Distribution</h3>
          <div echarts [options]="confidenceChart" class="h-[280px]"></div>
        </div>

        <!-- Fallback Categories -->
        <div class="bg-[#0F172A] rounded-2xl border border-slate-800 p-6">
          <h3 class="text-sm font-bold text-white mb-5" style="font-family: 'Figtree', sans-serif;">Top Fallback Categories</h3>
          <div echarts [options]="fallbackChart" class="h-[280px]"></div>
        </div>

        <!-- Suggestions List -->
        <div class="bg-[#0F172A] rounded-2xl border border-slate-800 p-6 max-h-[400px] overflow-y-auto custom-scrollbar">
          <h3 class="text-sm font-bold text-white mb-5" style="font-family: 'Figtree', sans-serif;">Recommended Actions</h3>
          <div class="space-y-3">
            <div *ngFor="let s of data()!.suggestions" class="p-4 bg-slate-800/40 rounded-xl border border-slate-700/50 hover:border-slate-600 transition-all cursor-pointer group">
              <div class="flex items-center justify-between mb-2">
                <span class="text-xs font-semibold text-white group-hover:text-indigo-300 transition-colors">{{s.category}}</span>
                <span [class]="getPriorityBadge(s.priority)">{{s.priority}}</span>
              </div>
              <p class="text-xs text-slate-400 leading-relaxed mb-3">{{s.suggestion}}</p>
              <div class="flex items-center gap-3 text-[10px] text-slate-500">
                <span>{{s.count}} queries</span>
                <span class="flex items-center gap-0.5" [class]="s.trend === 'up' ? 'text-rose-400' : s.trend === 'down' ? 'text-emerald-400' : 'text-slate-500'">
                  <svg *ngIf="s.trend === 'up'" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18"/></svg>
                  <svg *ngIf="s.trend === 'down'" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3"/></svg>
                  {{s.trend_pct}}%
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Knowledge Gaps Section -->
      <div *ngIf="!isLoading() && gapData()" class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Top Missing Topics -->
        <div class="bg-[#0F172A] rounded-2xl border border-slate-800 p-6">
          <div class="flex items-center gap-2 mb-5">
            <svg class="w-4 h-4 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>
            <h3 class="text-sm font-bold text-white" style="font-family: 'Figtree', sans-serif;">Top Missing Topics</h3>
            <span class="text-[10px] text-slate-500 ml-auto">Based on failed/low-confidence queries</span>
          </div>
          <div class="space-y-2.5">
            <div *ngFor="let t of gapData()!.top_missing_topics; let i = index" class="flex items-center gap-3">
              <span class="text-[10px] text-slate-600 w-4 text-right">{{i + 1}}</span>
              <div class="flex-1">
                <div class="flex items-center justify-between mb-1">
                  <span class="text-xs font-semibold text-slate-300">{{t.topic}}</span>
                  <span class="text-[10px] text-slate-500 font-mono">{{t.count}}x</span>
                </div>
                <div class="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div class="h-full rounded-full bg-gradient-to-r from-rose-500 to-orange-400 transition-all duration-500"
                    [style.width.%]="t.count / (gapData()!.top_missing_topics[0]?.count || 1) * 100"></div>
                </div>
              </div>
            </div>
            <div *ngIf="gapData()!.top_missing_topics.length === 0" class="text-center py-6">
              <p class="text-xs text-slate-600">No knowledge gaps detected yet</p>
            </div>
          </div>
        </div>

        <!-- Recent Failed Queries -->
        <div class="bg-[#0F172A] rounded-2xl border border-slate-800 p-6 max-h-[460px] overflow-y-auto custom-scrollbar">
          <div class="flex items-center gap-2 mb-5">
            <svg class="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"/></svg>
            <h3 class="text-sm font-bold text-white" style="font-family: 'Figtree', sans-serif;">Recent Failed Queries</h3>
          </div>
          <div class="space-y-3">
            <div *ngFor="let g of gapData()!.gaps" class="p-3 bg-slate-800/30 rounded-xl border border-slate-700/30 hover:border-slate-600/50 transition-all">
              <p class="text-xs text-slate-300 mb-2 leading-relaxed">"{{g.query}}"</p>
              <div class="flex items-center gap-3">
                <span [class]="getGapOutcomeBadge(g.outcome)">{{g.outcome?.replace('_', ' ') || 'Unknown'}}</span>
                <span *ngIf="g.confidence !== null" class="text-[10px] font-mono" [class]="(g.confidence ?? 0) < 0.3 ? 'text-rose-400' : 'text-amber-400'">
                  {{((g.confidence ?? 0) * 100).toFixed(0)}}%
                </span>
                <span class="text-[10px] text-slate-600 ml-auto">{{(g.timestamp || '').split('T')[0]}}</span>
              </div>
            </div>
            <div *ngIf="gapData()!.gaps.length === 0" class="text-center py-6">
              <svg class="w-8 h-8 text-emerald-500/30 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              <p class="text-xs text-slate-600">All queries resolved successfully!</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Loading -->
      <div *ngIf="isLoading()" class="grid grid-cols-1 md:grid-cols-4 gap-5">
        <div *ngFor="let _ of [1,2,3,4]" class="bg-slate-800/50 rounded-2xl border border-slate-700/50 p-5 animate-pulse">
          <div class="h-3 bg-slate-700 rounded w-20 mb-3"></div>
          <div class="h-7 bg-slate-700 rounded w-12 mb-2"></div>
          <div class="h-3 bg-slate-700 rounded w-24"></div>
        </div>
      </div>
    </div>
  `
})
export class InsightsComponent implements OnInit {
  data = signal<InsightsData | null>(null);
  gapData = signal<GapData | null>(null);
  csatData = signal<CsatStats | null>(null);
  isLoading = signal(true);

  confidenceChart: any = {};
  fallbackChart: any = {};

  constructor(
    private insightsService: InsightsService,
    private http: HttpClient,
  ) {}

  ngOnInit(): void {
    this.loadData();
  }

  refreshData(): void {
    this.loadData();
  }

  private loadData(): void {
    this.isLoading.set(true);
    this.insightsService.getInsights().subscribe({
      next: (data) => {
        this.data.set(data);
        this.buildCharts(data);
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false)
    });

    // Load knowledge gaps
    this.http.get<GapData>(`${environment.apiUrl}/api/v1/knowledge/gaps`).subscribe({
      next: (data) => this.gapData.set(data),
    });

    // Load CSAT stats
    this.http.get<CsatStats>(`${environment.apiUrl}/api/v1/feedback/stats`).subscribe({
      next: (data) => this.csatData.set(data),
    });
  }

  private buildCharts(data: InsightsData): void {
    // Confidence Distribution
    this.confidenceChart = {
      tooltip: { trigger: 'axis', backgroundColor: '#1E293B', borderColor: '#334155', textStyle: { color: '#F8FAFC', fontSize: 12 } },
      grid: { left: '3%', right: '5%', bottom: '3%', top: '5%', containLabel: true },
      xAxis: { type: 'category', data: data.confidence_distribution.map(c => c.range), axisLabel: { color: '#64748B', fontSize: 9, rotate: 35 }, axisLine: { lineStyle: { color: '#334155' } } },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1E293B', type: 'dashed' } }, axisLabel: { color: '#64748B' } },
      series: [{
        type: 'bar', data: data.confidence_distribution.map(c => c.count),
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#818cf8' }, { offset: 1, color: '#4f46e5' }
          ])
        },
        barWidth: '60%'
      }]
    };

    // Fallback Categories
    this.fallbackChart = {
      tooltip: { trigger: 'axis', backgroundColor: '#1E293B', borderColor: '#334155', textStyle: { color: '#F8FAFC', fontSize: 12 } },
      grid: { left: '3%', right: '5%', bottom: '3%', top: '5%', containLabel: true },
      xAxis: { type: 'value', splitLine: { lineStyle: { color: '#1E293B', type: 'dashed' } }, axisLabel: { color: '#64748B' } },
      yAxis: { type: 'category', data: data.fallback_categories.map(c => c.name), axisLabel: { color: '#94A3B8', fontSize: 11 }, axisLine: { lineStyle: { color: '#334155' } } },
      series: [{
        type: 'bar',
        data: data.fallback_categories.map((c, i) => ({
          value: c.count,
          itemStyle: {
            borderRadius: [0, 4, 4, 0],
            color: ['#f43f5e', '#f97316', '#eab308', '#6366f1', '#8b5cf6', '#06b6d4'][i] || '#6366f1'
          }
        })),
        barWidth: '55%'
      }]
    };
  }

  getPriorityBadge(priority: string): string {
    const base = 'text-[9px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider ';
    if (priority === 'high') return base + 'bg-rose-500/10 text-rose-400';
    if (priority === 'medium') return base + 'bg-amber-500/10 text-amber-400';
    return base + 'bg-slate-700 text-slate-400';
  }

  getGapOutcomeBadge(outcome: string): string {
    const base = 'text-[9px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider ';
    if (outcome === 'HUMAN_ESCALATED') return base + 'bg-amber-500/10 text-amber-400';
    if (outcome === 'AI_FALLBACK') return base + 'bg-indigo-500/10 text-indigo-400';
    if (outcome === 'DEGRADED') return base + 'bg-rose-500/10 text-rose-400';
    return base + 'bg-slate-700 text-slate-400';
  }
}

