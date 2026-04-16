import { Component, OnInit, OnDestroy, ChangeDetectionStrategy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts';
import { Subscription } from 'rxjs';
import { MetricsService } from '../../../core/services/metrics.service';
import { WebSocketService } from '../../../core/services/websocket.service';
import { DashboardMetrics } from '../../../shared/models';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, NgxEchartsDirective],
  providers: [provideEchartsCore({ echarts })],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="space-y-8">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-white tracking-tight" style="font-family: 'Figtree', sans-serif;">Support Overview</h1>
          <p class="text-slate-500 mt-1 text-sm">Real-time metrics for AI RAG support system</p>
        </div>
        <div class="flex gap-1.5 bg-slate-800/50 p-1 rounded-xl border border-slate-700/50">
           <button *ngFor="let range of timeRanges" (click)="activeRange.set(range)"
             [class]="activeRange() === range
               ? 'px-4 py-2 bg-indigo-600 shadow-sm rounded-lg text-xs font-semibold text-white transition-all cursor-pointer'
               : 'px-4 py-2 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 transition-all cursor-pointer'">
             {{range}}
           </button>
        </div>
      </div>

      <!-- Loading State -->
      <div *ngIf="isLoading()" class="grid grid-cols-1 md:grid-cols-4 gap-5">
        <div *ngFor="let _ of [1,2,3,4]" class="bg-slate-800/50 rounded-2xl border border-slate-700/50 p-6 animate-pulse">
          <div class="h-3 bg-slate-700 rounded w-24 mb-4"></div>
          <div class="h-8 bg-slate-700 rounded w-16 mb-3"></div>
          <div class="h-3 bg-slate-700 rounded w-28"></div>
        </div>
      </div>

      <!-- Key Metrics -->
      <div *ngIf="!isLoading() && metrics()" class="grid grid-cols-1 md:grid-cols-4 gap-5">
        <div class="bg-[#0F172A] p-6 rounded-2xl border border-slate-800 flex flex-col justify-center transition-all hover:border-slate-600 cursor-pointer group">
          <div class="text-slate-500 font-semibold text-xs mb-3 flex items-center gap-2 uppercase tracking-wider">
            <span class="w-2 h-2 rounded-full bg-slate-500"></span> Total Requests
          </div>
          <div class="text-3xl font-extrabold text-white tracking-tight">{{metrics()!.total_requests | number}}</div>
          <div class="text-xs text-emerald-400 mt-3 font-medium flex items-center bg-emerald-500/10 w-fit px-2 py-0.5 rounded-md">
            <svg class="w-3 h-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18"></path></svg>
            Active pipeline
          </div>
        </div>

        <div class="bg-[#0F172A] p-6 rounded-2xl border border-slate-800 flex flex-col justify-center transition-all hover:border-emerald-700 cursor-pointer group relative overflow-hidden">
          <div class="absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div class="text-slate-500 font-semibold text-xs mb-3 flex items-center gap-2 uppercase tracking-wider relative">
             <span class="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.6)]"></span> RAG Resolved
          </div>
          <div class="text-3xl font-extrabold text-white tracking-tight relative">{{metrics()!.rag_resolved}}</div>
          <div class="text-xs text-slate-400 mt-3 font-medium relative">{{metrics()!.rag_success_rate}}% success rate</div>
        </div>

        <div class="bg-[#0F172A] p-6 rounded-2xl border border-slate-800 flex flex-col justify-center transition-all hover:border-indigo-700 cursor-pointer group relative overflow-hidden">
          <div class="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div class="text-slate-500 font-semibold text-xs mb-3 flex items-center gap-2 uppercase tracking-wider relative">
             <span class="w-2 h-2 rounded-full bg-indigo-500"></span> GenAI Escalated
          </div>
          <div class="text-3xl font-extrabold text-white tracking-tight relative">{{metrics()!.ai_fallback}}</div>
          <div class="text-xs text-slate-400 mt-3 font-medium relative">{{metrics()!.fallback_rate}}% fallback rate</div>
        </div>

        <div class="bg-gradient-to-br from-rose-900/30 to-[#0F172A] p-6 rounded-2xl border border-rose-800/50 flex flex-col justify-center relative overflow-hidden transition-all hover:border-rose-600 cursor-pointer">
          <div class="relative z-10">
            <div class="text-rose-400 font-semibold text-xs mb-3 flex items-center gap-2 uppercase tracking-wider">
               <span class="w-2 h-2 rounded-full bg-rose-500 animate-pulse shadow-[0_0_6px_rgba(244,63,94,0.6)]"></span> Human Required
            </div>
            <div class="text-3xl font-extrabold text-rose-300 tracking-tight">{{metrics()!.human_escalated}}</div>
            <div class="text-xs text-rose-400/80 mt-3 font-medium flex items-center bg-rose-500/10 w-fit px-2 py-0.5 rounded-md">
              {{metrics()!.escalation_rate}}% manual intervention
            </div>
          </div>
        </div>
      </div>

      <!-- Charts Section -->
      <div *ngIf="!isLoading()" class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div class="bg-[#0F172A] p-6 rounded-2xl border border-slate-800 col-span-2">
           <div class="flex justify-between items-center mb-6">
             <h3 class="text-base font-bold text-white tracking-tight" style="font-family: 'Figtree', sans-serif;">System Performance Timeline</h3>
           </div>
           <div echarts [options]="areaChart" class="h-[350px]"></div>
        </div>
        <div class="bg-[#0F172A] p-6 rounded-2xl border border-slate-800">
           <div class="flex justify-between items-center mb-6">
             <h3 class="text-base font-bold text-white tracking-tight" style="font-family: 'Figtree', sans-serif;">Resolution Breakdown</h3>
           </div>
           <div echarts [options]="pieChart" class="h-[350px]"></div>
        </div>
      </div>
    </div>
  `
})
export class DashboardComponent implements OnInit, OnDestroy {
  metrics = signal<DashboardMetrics | null>(null);
  isLoading = signal(true);
  activeRange = signal('24 Hours');
  timeRanges = ['24 Hours', '7 Days', '30 Days'];

  areaChart: any = {};
  pieChart: any = {};

  private subs: Subscription[] = [];

  constructor(
    private metricsService: MetricsService,
    private wsService: WebSocketService
  ) {}

  ngOnInit(): void {
    this.loadMetrics();

    // Listen for real-time metric updates via WebSocket
    this.subs.push(
      this.wsService.getMetricUpdates().subscribe(update => {
        const current = this.metrics();
        if (current) {
          this.metrics.set({
            ...current,
            total_requests: update.total_requests,
            rag_resolved: update.rag_resolved,
            ai_fallback: update.ai_fallback,
            human_escalated: update.human_escalated,
            errors: update.errors,
            open_tickets: update.open_tickets,
          });
        }
      })
    );
  }

  private loadMetrics(): void {
    this.isLoading.set(true);
    this.subs.push(
      this.metricsService.getMetrics().subscribe({
        next: (data) => {
          this.metrics.set(data);
          this.buildCharts(data);
          this.isLoading.set(false);
        },
        error: () => this.isLoading.set(false)
      })
    );
  }

  private buildCharts(data: DashboardMetrics): void {
    const days = data.time_series.map(t => t.day);
    const confidences = data.time_series.map(t => t.rag_confidence);
    const responseTimes = data.time_series.map(t => t.response_time);

    this.areaChart = {
      tooltip: { trigger: 'axis', backgroundColor: '#1E293B', borderColor: '#334155', textStyle: { color: '#F8FAFC', fontSize: 12 }, padding: 12 },
      legend: { data: ['RAG Confidence', 'Response Time (ms)'], bottom: 0, icon: 'circle', textStyle: { color: '#94A3B8' } },
      grid: { left: '3%', right: '4%', bottom: '12%', top: '5%', containLabel: true },
      xAxis: {
        type: 'category', boundaryGap: false, data: days,
        axisLine: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#64748B' }
      },
      yAxis: [
        { type: 'value', name: 'Confidence (%)', splitLine: { lineStyle: { color: '#1E293B', type: 'dashed' } }, axisLabel: { color: '#64748B' }, nameTextStyle: { color: '#64748B', padding: [0, 0, 0, 20] } },
        { type: 'value', name: 'ms', splitLine: { show: false }, axisLabel: { color: '#64748B' }, nameTextStyle: { color: '#64748B' } }
      ],
      series: [
        {
          name: 'RAG Confidence', type: 'line', smooth: 0.4, symbol: 'none',
          lineStyle: { width: 3, color: '#6366f1' },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(99,102,241,0.25)' }, { offset: 1, color: 'rgba(99,102,241,0.02)' }
          ])},
          data: confidences
        },
        {
          name: 'Response Time (ms)', type: 'line', smooth: 0.4, symbol: 'none',
          yAxisIndex: 1, lineStyle: { width: 3, color: '#fb923c', type: 'dashed' },
          data: responseTimes
        }
      ]
    };

    this.pieChart = {
      tooltip: { trigger: 'item', backgroundColor: '#1E293B', borderColor: '#334155', textStyle: { color: '#F8FAFC' } },
      legend: { bottom: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: '#94A3B8' }, icon: 'circle' },
      series: [{
        name: 'Resolution', type: 'pie', radius: ['55%', '80%'], center: ['50%', '42%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 8, borderColor: '#0F172A', borderWidth: 4 },
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 22, fontWeight: 'bold', color: '#F8FAFC' } },
        labelLine: { show: false },
        data: [
          { value: data.rag_resolved, name: 'RAG Resolved', itemStyle: { color: '#10b981' } },
          { value: data.ai_fallback, name: 'GenAI Fallback', itemStyle: { color: '#6366f1' } },
          { value: data.human_escalated, name: 'Human Agent', itemStyle: { color: '#f43f5e' } },
        ]
      }]
    };
  }

  ngOnDestroy(): void {
    this.subs.forEach(s => s.unsubscribe());
  }
}
