import { Component, OnInit, signal, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts';
import { InsightsService } from '../../../core/services/insights.service';
import { InsightsData, InsightSuggestion } from '../../../shared/models';

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
      <div *ngIf="!isLoading() && data()" class="grid grid-cols-1 md:grid-cols-4 gap-5">
        <div class="bg-[#0F172A] p-5 rounded-2xl border border-slate-800">
          <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">Knowledge Gaps</div>
          <div class="text-2xl font-extrabold text-Rose-300" style="color: #fb7185;">{{data()!.knowledge_gaps}}</div>
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
  isLoading = signal(true);

  confidenceChart: any = {};
  fallbackChart: any = {};

  constructor(private insightsService: InsightsService) {}

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
}
