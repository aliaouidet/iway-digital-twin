import { Component, OnInit, ChangeDetectionStrategy, signal, DestroyRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { auditTime } from 'rxjs/operators';
import { MetricsService, OpsMetrics } from '../../../core/services/metrics.service';
import { WebSocketService } from '../../../core/services/websocket.service';
import { DashboardMetrics } from '../../../shared/models';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, NgxEchartsDirective],
  providers: [provideEchartsCore({ echarts })],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard.component.html'
})
export class DashboardComponent implements OnInit {
  metrics = signal<DashboardMetrics | null>(null);
  ops = signal<OpsMetrics | null>(null);
  isLoading = signal(true);

  // Date picker state
  startDate = signal<string>('');
  endDate = signal<string>('');
  activePreset = signal<string>('all');

  areaChart: any = {};
  pieChart: any = {};
  trafficChart: any = {};
  dailyVolumeChart: any = {};

  private destroyRef = inject(DestroyRef);

  constructor(
    private metricsService: MetricsService,
    private wsService: WebSocketService
  ) {}

  ngOnInit(): void {
    this.loadMetrics();

    // All real-time events trigger a fresh PostgreSQL read.
    // PostgreSQL is the single source of truth — no partial WS overwrites.
    const refresh = () => this.loadMetrics();

    // METRIC_UPDATE is pushed by the backend every ~10s forever — auditTime
    // caps the refresh (2 HTTP GETs + full chart rebuild) to once per 60s.
    // Rare, meaningful events (escalation/resolution) still refresh instantly.
    this.wsService.getMetricUpdates().pipe(
      auditTime(60_000),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(refresh);
    this.wsService.getEscalationUpdates().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(refresh);
    this.wsService.getSessionUpdates().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(event => {
      if (event.type === 'SESSION_RESOLVED') refresh();
    });
  }

  // --- Date Picker ---

  onPreset(preset: string): void {
    this.activePreset.set(preset);
    const today = new Date();

    if (preset === 'all') {
      this.startDate.set('');
      this.endDate.set('');
    } else if (preset === 'today') {
      const d = this.formatDate(today);
      this.startDate.set(d);
      this.endDate.set(d);
    } else if (preset === '7d') {
      const start = new Date(today);
      start.setDate(start.getDate() - 7);
      this.startDate.set(this.formatDate(start));
      this.endDate.set(this.formatDate(today));
    } else if (preset === '30d') {
      const start = new Date(today);
      start.setDate(start.getDate() - 30);
      this.startDate.set(this.formatDate(start));
      this.endDate.set(this.formatDate(today));
    }

    this.loadMetrics();
  }

  onDateChange(type: 'start' | 'end', event: Event): void {
    const val = (event.target as HTMLInputElement).value;
    if (type === 'start') this.startDate.set(val);
    else this.endDate.set(val);
    this.activePreset.set('custom');
    this.loadMetrics();
  }

  private formatDate(d: Date): string {
    // Local date, NOT toISOString() (UTC) — otherwise "today" selects
    // yesterday between 00:00 and 01:00 Tunisia time (UTC+1).
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  getTodayStr(): string {
    return this.formatDate(new Date());
  }

  // --- Data Loading ---

  private loadMetrics(): void {
    this.isLoading.set(true);
    const s = this.startDate() || undefined;
    const e = this.endDate() || undefined;

    this.metricsService.getMetrics(s, e).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => {
        this.metrics.set(data);
        this.buildCharts(data);
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false)
    });

    // Load hourly traffic (always for today or selected start date)
    const trafficDate = this.activePreset() === 'today' ? this.startDate() : undefined;
    this.metricsService.getHourlyTraffic(trafficDate || undefined).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => this.buildTrafficChart(data.hourly),
    });

    // AI-Ops snapshot (tokens, cache, escalation paths, node latencies, circuits)
    this.metricsService.getOpsMetrics().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => this.ops.set(data),
      error: () => this.ops.set(null),
    });
  }

  // --- AI-Ops helpers ---

  escalationEntries(): { label: string; count: number }[] {
    const labels: { [k: string]: string } = {
      graph: 'Explicit request',
      low_confidence: 'Low confidence',
      degraded: 'Service degraded',
      manual: 'Manual button',
    };
    const esc = this.ops()?.escalations || {};
    return Object.entries(esc)
      .map(([path, count]) => ({ label: labels[path] || path, count: count as number }))
      .sort((a, b) => b.count - a.count);
  }

  circuitEntries(): { name: string; state: string }[] {
    const circuits = this.ops()?.circuits || {};
    return Object.values(circuits).map(c => ({ name: c.name, state: c.state }));
  }

  circuitClass(state: string): string {
    if (state === 'open') return 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400';
    if (state === 'half_open') return 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400';
    return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400';
  }

  // --- Charts ---

  private buildCharts(data: DashboardMetrics): void {
    const days = data.time_series.map(t => t.day);
    const confidences = data.time_series.map(t => t.rag_confidence);
    const responseTimes = data.time_series.map(t => t.response_time);
    const dailyTraffic = data.time_series.map(t => t.total_traces);

    this.areaChart = {
      tooltip: {
        trigger: 'axis', backgroundColor: '#1E293B', borderColor: '#334155',
        textStyle: { color: '#F8FAFC', fontSize: 12 }, padding: 12,
        formatter: (params: any) => {
          let html = `<div style="font-weight:600;margin-bottom:6px">${params[0]?.axisValue}</div>`;
          for (const p of params) {
            const dot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color};margin-right:6px"></span>`;
            if (p.seriesName === 'RAG Confidence') {
              html += `${dot}${p.seriesName}: <b>${p.value}%</b><br/>`;
            } else {
              html += `${dot}${p.seriesName}: <b>${(p.value / 1000).toFixed(1)}s</b> (${p.value.toLocaleString()}ms)<br/>`;
            }
          }
          return html;
        }
      },
      legend: { data: ['RAG Confidence', 'Avg Response Time'], bottom: 0, icon: 'circle', textStyle: { color: '#94A3B8' } },
      grid: { left: '3%', right: '5%', bottom: '14%', top: '8%', containLabel: true },
      xAxis: {
        type: 'category', boundaryGap: false, data: days,
        axisLine: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#64748B', fontSize: 11 }
      },
      yAxis: [
        {
          type: 'value', name: 'Confidence (%)', min: 0, max: 100,
          splitLine: { lineStyle: { color: '#1E293B', type: 'dashed' } },
          axisLabel: { color: '#64748B', formatter: '{value}%' },
          nameTextStyle: { color: '#64748B', padding: [0, 0, 0, 20] }
        },
        {
          type: 'value', name: 'Response Time',
          splitLine: { show: false },
          axisLabel: { color: '#64748B', formatter: (v: number) => `${(v / 1000).toFixed(0)}s` },
          nameTextStyle: { color: '#64748B' }
        }
      ],
      series: [
        {
          name: 'RAG Confidence', type: 'line', smooth: 0.3,
          symbol: 'circle', symbolSize: 8, showSymbol: true,
          lineStyle: { width: 3, color: '#818cf8' },
          itemStyle: { color: '#818cf8', borderColor: '#fff', borderWidth: 2 },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(129,140,248,0.2)' }, { offset: 1, color: 'rgba(129,140,248,0.02)' }
          ])},
          data: confidences
        },
        {
          name: 'Avg Response Time', type: 'line', smooth: 0.3,
          symbol: 'diamond', symbolSize: 8, showSymbol: true,
          yAxisIndex: 1,
          lineStyle: { width: 3, color: '#fb923c' },
          itemStyle: { color: '#fb923c', borderColor: '#fff', borderWidth: 2 },
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
        itemStyle: { borderRadius: 8, borderColor: '#0B1120', borderWidth: 4 },
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 22, fontWeight: 'bold', color: '#F8FAFC' }, itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
        labelLine: { show: false },
        data: [
          { value: data.rag_resolved, name: 'RAG Resolved', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{offset: 0, color: '#34d399'}, {offset: 1, color: '#059669'}]) } },
          { value: data.ai_fallback, name: 'GenAI Fallback', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{offset: 0, color: '#818cf8'}, {offset: 1, color: '#4f46e5'}]) } },
          { value: data.human_escalated, name: 'Human Agent', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{offset: 0, color: '#fb7185'}, {offset: 1, color: '#e11d48'}]) } },
          { value: data.errors, name: 'Errors', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{offset: 0, color: '#fbbf24'}, {offset: 1, color: '#d97706'}]) } },
        ].filter(d => d.value > 0)
      }]
    };

    // --- Daily Volume Bar Chart ---
    this.dailyVolumeChart = {
      tooltip: {
        trigger: 'axis', backgroundColor: '#1E293B', borderColor: '#334155',
        textStyle: { color: '#F8FAFC', fontSize: 12 },
        formatter: (params: any) => {
          const p = params[0];
          return `<div style="font-weight:600">${p.axisValue}</div><b>${p.value}</b> queries`;
        }
      },
      grid: { left: '3%', right: '4%', bottom: '5%', top: '12%', containLabel: true },
      xAxis: {
        type: 'category', data: days,
        axisLine: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#64748B', fontSize: 10 }
      },
      yAxis: {
        type: 'value', minInterval: 1,
        splitLine: { lineStyle: { color: '#1E293B', type: 'dashed' } },
        axisLabel: { color: '#64748B' }
      },
      series: [{
        type: 'bar', barWidth: '50%',
        label: { show: true, position: 'top', color: '#94A3B8', fontSize: 11, fontWeight: 'bold' },
        itemStyle: {
          borderRadius: [6, 6, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#34d399' }, { offset: 1, color: '#059669' }
          ])
        },
        data: dailyTraffic
      }]
    };
  }

  private buildTrafficChart(hourly: { hour: number; label: string; count: number }[]): void {
    const labels = hourly.map(h => h.label);
    const counts = hourly.map(h => h.count);
    const maxCount = Math.max(...counts, 1);

    this.trafficChart = {
      tooltip: { trigger: 'axis', backgroundColor: '#1E293B', borderColor: '#334155', textStyle: { color: '#F8FAFC', fontSize: 12 } },
      grid: { left: '3%', right: '4%', bottom: '5%', top: '8%', containLabel: true },
      xAxis: {
        type: 'category', data: labels,
        axisLine: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#64748B', fontSize: 9, interval: 1 }
      },
      yAxis: {
        type: 'value', splitLine: { lineStyle: { color: '#1E293B', type: 'dashed' } },
        axisLabel: { color: '#64748B' }, minInterval: 1
      },
      series: [{
        type: 'bar', data: counts.map(c => ({
          value: c,
          itemStyle: {
            borderRadius: [4, 4, 0, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: c > maxCount * 0.7 ? '#f43f5e' : c > maxCount * 0.4 ? '#fbbf24' : '#818cf8' },
              { offset: 1, color: c > maxCount * 0.7 ? '#881337' : c > maxCount * 0.4 ? '#92400e' : '#312e81' }
            ])
          }
        })),
        barWidth: '60%',
      }]
    };
  }
}
