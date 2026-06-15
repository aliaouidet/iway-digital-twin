import { Component, OnInit, ChangeDetectionStrategy, signal, computed, DestroyRef, inject, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { auditTime } from 'rxjs/operators';
import { MetricsService, OpsMetrics } from '../../../core/services/metrics.service';
import { WebSocketService } from '../../../core/services/websocket.service';
import { ThemeService } from '../../../core/services/theme.service';
import { ToastService } from '../../../core/services/toast.service';
import { DashboardMetrics, FeedbackStats } from '../../../shared/models';
import { ErrorBannerComponent } from '../../../shared/components/error-banner.component';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, NgxEchartsDirective, ErrorBannerComponent],
  providers: [provideEchartsCore({ echarts })],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard.component.html'
})
export class DashboardComponent implements OnInit {
  metrics = signal<DashboardMetrics | null>(null);
  ops = signal<OpsMetrics | null>(null);
  feedback = signal<FeedbackStats | null>(null);
  isLoading = signal(true);     // first load → skeletons
  isSyncing = signal(false);    // background WS/manual refresh → subtle pulse
  error = signal<string | null>(null);
  lastUpdated = signal<Date | null>(null);

  // Live controls
  autoRefresh = signal(true);
  newEscalations = signal(0);

  // Date picker state
  startDate = signal<string>('');
  endDate = signal<string>('');
  activePreset = signal<string>('all');

  areaChart: any = {};
  pieChart: any = {};
  trafficChart: any = {};
  dailyVolumeChart: any = {};
  funnelChart: any = {};
  healthGauge: any = {};

  // Rough blended price for gemini-2.5-flash (USD per 1M tokens). Display-only
  // estimate — adjust here if the model/pricing changes.
  private readonly COST_PER_1M_TOKENS = 0.30;

  /** Composite 0–100 health score: success + confidence + latency + reliability. */
  healthScore = computed<number>(() => {
    const m = this.metrics();
    if (!m) return 0;
    const o = this.ops();
    const success = m.rag_success_rate ?? 0;
    const confidence = m.avg_confidence ?? 0;
    const ms = m.avg_response_time_ms ?? 0;
    const latency = ms <= 5000 ? 100 : ms >= 20000 ? 0 : 100 - ((ms - 5000) / 15000) * 100;
    const errorOk = 100 - (m.error_rate ?? 0);
    let score = 0.4 * success + 0.2 * confidence + 0.2 * latency + 0.2 * errorOk;
    if (o) {
      const circuitsOpen = Object.values(o.circuits || {}).some(c => c.state === 'open');
      if (circuitsOpen) score *= 0.6;
      if (o.persistence?.degraded) score -= 20;
    }
    return Math.max(0, Math.min(100, Math.round(score)));
  });

  /** Estimated LLM spend so far, from durable token counts. */
  estCost = computed<number>(() => {
    const o = this.ops();
    if (!o) return 0;
    return (o.tokens.total_tokens / 1_000_000) * this.COST_PER_1M_TOKENS;
  });

  private destroyRef = inject(DestroyRef);
  private router = inject(Router);
  private toast = inject(ToastService);

  private lastHourly: { hour: number; label: string; count: number }[] | null = null;

  constructor(
    private metricsService: MetricsService,
    private wsService: WebSocketService,
    private themeService: ThemeService,
  ) {
    // Rebuild charts when the theme flips — chart colors were previously
    // hardcoded dark and unreadable in light mode.
    effect(() => {
      this.themeService.theme(); // track
      const m = this.metrics();
      if (m) this.buildCharts(m);
      if (this.lastHourly) this.buildTrafficChart(this.lastHourly);
      // healthScore() reads metrics()+ops(), so this also rebuilds the gauge
      // when the Ops snapshot arrives — not only on theme/metrics change.
      this.buildHealthGauge();
    });
  }

  /** ECharts colors derived from the active theme. */
  private chartPalette() {
    const dark = this.themeService.isDark();
    return {
      tooltipBg: dark ? '#1E293B' : '#FFFFFF',
      tooltipBorder: dark ? '#334155' : '#E2E8F0',
      tooltipText: dark ? '#F8FAFC' : '#0F172A',
      axisLine: dark ? '#334155' : '#CBD5E1',
      axisLabel: '#64748B',
      splitLine: dark ? '#1E293B' : '#E2E8F0',
      legendText: dark ? '#94A3B8' : '#475569',
      barLabel: dark ? '#94A3B8' : '#475569',
      pieBorder: dark ? '#0B1120' : '#FFFFFF',
      emphasisText: dark ? '#F8FAFC' : '#0F172A',
    };
  }

  ngOnInit(): void {
    this.loadMetrics();

    // All real-time events trigger a fresh PostgreSQL read (single source of
    // truth — no partial WS overwrites). Background refreshes never flash the
    // skeletons and respect the auto-refresh toggle.
    const refresh = () => { if (this.autoRefresh()) this.loadMetrics(true); };

    // METRIC_UPDATE is pushed by the backend every ~10s forever — auditTime
    // caps the refresh (HTTP GETs + chart rebuild) to once per 60s.
    this.wsService.getMetricUpdates().pipe(
      auditTime(60_000),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(refresh);

    // A fresh escalation is rare + meaningful: toast it, bump the unread badge,
    // and refresh instantly so the queue-depth card stays truthful.
    this.wsService.getEscalationUpdates().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(payload => {
      this.newEscalations.update(n => n + 1);
      const who = payload?.user_name || payload?.user_matricule || 'a client';
      this.toast.show(`New escalation — ${who}`, 'warning');
      if (this.autoRefresh()) this.loadMetrics(true);
    });

    this.wsService.getSessionUpdates().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(event => {
      if (event.type === 'SESSION_RESOLVED' && this.autoRefresh()) this.loadMetrics(true);
    });
  }

  // --- Live controls ---

  toggleAutoRefresh(): void {
    this.autoRefresh.update(v => !v);
    if (this.autoRefresh()) this.loadMetrics(true);
  }

  manualRefresh(): void {
    this.newEscalations.set(0);
    this.loadMetrics(true);
  }

  /** RAG Resolved → filtered Logs; Human Escalated → Tickets; etc. */
  drillToLogs(outcome: string): void {
    this.router.navigate(['/admin/logs'], { queryParams: { outcome } });
  }

  drillToTickets(tab: string): void {
    this.newEscalations.set(0);
    this.router.navigate(['/admin/tickets'], { queryParams: { tab } });
  }

  // --- Period-over-period deltas (from the backend comparison block) ---

  /** Signed % change of a metric vs the previous window. null = no comparison. */
  deltaPct(key: 'total_requests' | 'rag_success_rate' | 'escalation_rate' | 'avg_confidence' | 'avg_response_time_ms'): number | null {
    const m = this.metrics();
    const c = m?.comparison;
    if (!m || !c) return null;
    const prev = c[key];
    const cur = (m as any)[key] as number;
    if (prev === undefined || prev === null || prev === 0) return cur > 0 ? 100 : null;
    const raw = Math.round(((cur - prev) / prev) * 100);
    return Math.max(-999, Math.min(999, raw)); // clamp absurd swings from tiny prior windows

  }

  /** Tailwind class for a delta chip — green when the move is in the good direction. */
  deltaClass(pct: number | null, higherIsGood: boolean): string {
    if (pct === null || pct === 0) return 'text-slate-400 dark:text-slate-500';
    const good = higherIsGood ? pct > 0 : pct < 0;
    return good ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-500 dark:text-rose-400';
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

  loadMetrics(background = false): void {
    // First load shows skeletons; background (WS/manual) refreshes just pulse.
    if (background) this.isSyncing.set(true);
    else this.isLoading.set(true);
    this.error.set(null);
    const s = this.startDate() || undefined;
    const e = this.endDate() || undefined;

    this.metricsService.getMetrics(s, e).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => {
        this.metrics.set(data);
        this.buildCharts(data);
        this.buildHealthGauge();
        this.lastUpdated.set(new Date());
        this.isLoading.set(false);
        this.isSyncing.set(false);
      },
      error: () => {
        this.error.set('Failed to load dashboard metrics.');
        this.isLoading.set(false);
        this.isSyncing.set(false);
      }
    });

    // CSAT snapshot (thumbs feedback) — only on a foreground load (initial/manual);
    // it barely changes, so we skip it on the 60s background + per-escalation refreshes.
    if (!background) {
      this.metricsService.getFeedbackStats().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (data) => this.feedback.set(data),
        error: () => this.feedback.set(null),
      });
    }

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

  /** Themed ECharts toolbox (save-as-image / data view / zoom) — adds interactivity. */
  private chartToolbox(features: any): any {
    const p = this.chartPalette();
    return {
      show: true, right: 8, top: -2, itemSize: 14, itemGap: 8,
      iconStyle: { borderColor: p.axisLabel },
      emphasis: { iconStyle: { borderColor: '#6366f1' } },
      feature: features,
    };
  }

  private buildCharts(data: DashboardMetrics): void {
    const p = this.chartPalette();
    const days = data.time_series.map(t => t.day);
    const confidences = data.time_series.map(t => t.rag_confidence);
    const responseTimes = data.time_series.map(t => t.response_time);
    const dailyTraffic = data.time_series.map(t => t.total_traces);

    this.areaChart = {
      tooltip: {
        trigger: 'axis', backgroundColor: p.tooltipBg, borderColor: p.tooltipBorder,
        textStyle: { color: p.tooltipText, fontSize: 12 }, padding: 12,
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
      legend: { data: ['RAG Confidence', 'Avg Response Time'], bottom: 0, icon: 'circle', textStyle: { color: p.legendText } },
      // Pin the toolbox into a dedicated top-right header band so the icons clear
      // the right y-axis name ("Response Time") — the shared chartToolbox() default
      // (top:-2) collides with axis names on this dual-axis chart.
      toolbox: {
        ...this.chartToolbox({
          dataZoom: { title: { zoom: 'Box zoom', back: 'Reset zoom' }, yAxisIndex: 'none' },
          restore: { title: 'Reset' },
          saveAsImage: { title: 'Save PNG', backgroundColor: p.tooltipBg },
        }),
        top: 2, right: 4,
      },
      dataZoom: [{ type: 'inside', throttle: 50 }],  // scroll / pinch to zoom the timeline
      grid: { left: '3%', right: '5%', bottom: '14%', top: '20%', containLabel: true },
      xAxis: {
        type: 'category', boundaryGap: false, data: days,
        axisLine: { lineStyle: { color: p.axisLine } },
        axisLabel: { color: p.axisLabel, fontSize: 11 }
      },
      yAxis: [
        {
          type: 'value', name: 'Confidence (%)', min: 0, max: 100,
          splitLine: { lineStyle: { color: p.splitLine, type: 'dashed' } },
          axisLabel: { color: p.axisLabel, formatter: '{value}%' },
          nameTextStyle: { color: p.axisLabel, padding: [0, 0, 0, 20] }
        },
        {
          type: 'value', name: 'Response Time',
          splitLine: { show: false },
          axisLabel: { color: p.axisLabel, formatter: (v: number) => `${(v / 1000).toFixed(0)}s` },
          nameTextStyle: { color: p.axisLabel }
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
      tooltip: { trigger: 'item', backgroundColor: p.tooltipBg, borderColor: p.tooltipBorder, textStyle: { color: p.tooltipText }, formatter: '{b}<br/><b>{c}</b> ({d}%)' },
      legend: { bottom: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: p.legendText }, icon: 'circle' },
      toolbox: this.chartToolbox({ saveAsImage: { title: 'Save PNG', backgroundColor: p.tooltipBg } }),
      series: [{
        name: 'Resolution', type: 'pie', radius: ['55%', '80%'], center: ['50%', '45%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 8, borderColor: p.pieBorder, borderWidth: 4 },
        // No on-chart label — the tooltip already carries name/value/percent, so a
        // second label drawn over the donut is redundant. Hover just pops the segment.
        label: { show: false },
        emphasis: {
          label: { show: false },
          itemStyle: { shadowBlur: 14, shadowColor: 'rgba(0,0,0,0.25)' },
        },
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
        trigger: 'axis', backgroundColor: p.tooltipBg, borderColor: p.tooltipBorder,
        textStyle: { color: p.tooltipText, fontSize: 12 },
        formatter: (params: any) => {
          const p = params[0];
          return `<div style="font-weight:600">${p.axisValue}</div><b>${p.value}</b> queries`;
        }
      },
      toolbox: this.chartToolbox({
        dataView: { title: 'Data', readOnly: true, backgroundColor: p.tooltipBg, textColor: p.tooltipText, lang: ['Daily volume', 'Close', ''] },
        saveAsImage: { title: 'Save PNG', backgroundColor: p.tooltipBg },
      }),
      grid: { left: '3%', right: '4%', bottom: '5%', top: '18%', containLabel: true },
      xAxis: {
        type: 'category', data: days,
        axisLine: { lineStyle: { color: p.axisLine } },
        axisLabel: { color: p.axisLabel, fontSize: 10 }
      },
      yAxis: {
        type: 'value', minInterval: 1,
        splitLine: { lineStyle: { color: p.splitLine, type: 'dashed' } },
        axisLabel: { color: p.axisLabel }
      },
      series: [{
        type: 'bar', barWidth: '50%',
        label: { show: true, position: 'top', color: p.barLabel, fontSize: 11, fontWeight: 'bold' },
        itemStyle: {
          borderRadius: [6, 6, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#34d399' }, { offset: 1, color: '#059669' }
          ])
        },
        data: dailyTraffic
      }]
    };

    // --- Resolution / deflection funnel (nested, decreasing stages) ---
    const total = data.total_requests;
    const contained = Math.max(total - data.human_escalated, 0);
    this.funnelChart = {
      tooltip: {
        trigger: 'item', backgroundColor: p.tooltipBg, borderColor: p.tooltipBorder,
        textStyle: { color: p.tooltipText, fontSize: 12 }, formatter: '{b}<br/><b>{c}</b> ({d}%)'
      },
      toolbox: this.chartToolbox({ saveAsImage: { title: 'Save PNG', backgroundColor: p.tooltipBg } }),
      series: [{
        type: 'funnel', left: '8%', right: '8%', top: 28, bottom: 12,
        minSize: '34%', maxSize: '100%', sort: 'descending', gap: 3,
        label: { show: true, position: 'inside', color: '#fff', fontWeight: 'bold', fontSize: 12 },
        labelLine: { show: false },
        itemStyle: { borderColor: p.pieBorder, borderWidth: 2 },
        emphasis: { label: { fontSize: 14 } },
        data: [
          { value: total, name: 'Requests', itemStyle: { color: '#64748b' } },
          { value: contained, name: 'AI-Contained', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#818cf8' }, { offset: 1, color: '#4f46e5' }]) } },
          { value: data.rag_resolved, name: 'RAG-Resolved', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#34d399' }, { offset: 1, color: '#059669' }]) } },
        ],
      }],
    };
  }

  /** Radial gauge of the composite health score (rebuilt by the theme effect). */
  private buildHealthGauge(): void {
    const p = this.chartPalette();
    const score = this.healthScore();
    const color = score >= 80 ? '#10b981' : score >= 50 ? '#fbbf24' : '#f43f5e';
    this.healthGauge = {
      series: [{
        type: 'gauge', startAngle: 210, endAngle: -30, min: 0, max: 100,
        radius: '100%', center: ['50%', '62%'],
        progress: { show: true, width: 12, roundCap: true, itemStyle: { color } },
        axisLine: { lineStyle: { width: 12, color: [[1, p.splitLine]] } },
        pointer: { show: false }, axisTick: { show: false }, splitLine: { show: false },
        axisLabel: { show: false }, anchor: { show: false }, title: { show: false },
        detail: {
          valueAnimation: true, fontSize: 30, fontWeight: 'bolder',
          offsetCenter: [0, '0%'], formatter: '{value}', color,
        },
        data: [{ value: score }],
      }],
    };
  }

  private buildTrafficChart(hourly: { hour: number; label: string; count: number }[]): void {
    this.lastHourly = hourly;
    const p = this.chartPalette();
    const labels = hourly.map(h => h.label);
    const counts = hourly.map(h => h.count);
    const maxCount = Math.max(...counts, 1);

    this.trafficChart = {
      tooltip: { trigger: 'axis', backgroundColor: p.tooltipBg, borderColor: p.tooltipBorder, textStyle: { color: p.tooltipText, fontSize: 12 } },
      toolbox: this.chartToolbox({ saveAsImage: { title: 'Save PNG', backgroundColor: p.tooltipBg } }),
      grid: { left: '3%', right: '4%', bottom: '5%', top: '18%', containLabel: true },
      xAxis: {
        type: 'category', data: labels,
        axisLine: { lineStyle: { color: p.axisLine } },
        axisLabel: { color: p.axisLabel, fontSize: 9, interval: 1 }
      },
      yAxis: {
        type: 'value', splitLine: { lineStyle: { color: p.splitLine, type: 'dashed' } },
        axisLabel: { color: p.axisLabel }, minInterval: 1
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
