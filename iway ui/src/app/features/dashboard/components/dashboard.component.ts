import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, NgxEchartsDirective],
  providers: [
    provideEchartsCore({ echarts })
  ],
  template: `
    <div class="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-3xl font-bold text-slate-800 tracking-tight">Support Overview</h1>
          <p class="text-slate-500 mt-1">Real-time metrics for AI RAG support system</p>
        </div>
        <div class="flex gap-2 bg-slate-100 p-1 rounded-xl">
           <button class="px-5 py-2.5 bg-white shadow-sm border-slate-200 rounded-lg text-sm font-semibold text-slate-700 transition">24 Hours</button>
           <button class="px-5 py-2.5 rounded-lg text-sm font-semibold text-slate-500 hover:text-slate-700 transition">7 Days</button>
           <button class="px-5 py-2.5 rounded-lg text-sm font-semibold text-slate-500 hover:text-slate-700 transition">30 Days</button>
        </div>
      </div>

      <!-- Key Metrics -->
      <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex flex-col justify-center transition-all hover:shadow-md hover:-translate-y-1 cursor-pointer">
          <div class="text-slate-500 font-semibold text-sm mb-3 flex items-center gap-2 uppercase tracking-wider">
            <span class="w-2.5 h-2.5 rounded-full bg-slate-400"></span> Total Requests
          </div>
          <div class="text-4xl font-extrabold text-slate-800 tracking-tight">12,458</div>
          <div class="text-sm text-emerald-600 mt-3 font-medium flex items-center bg-emerald-50 w-fit px-2 py-0.5 rounded-md">
            <svg class="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18"></path></svg>
            12% vs last week
          </div>
        </div>
        
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex flex-col justify-center transition-all hover:shadow-md hover:-translate-y-1 cursor-pointer group">
          <div class="absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div class="text-slate-500 font-semibold text-sm mb-3 flex items-center gap-2 uppercase tracking-wider relative">
             <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]"></span> RAG Resolved
          </div>
          <div class="text-4xl font-extrabold text-slate-800 tracking-tight relative">8,902</div>
          <div class="text-sm text-slate-500 mt-3 font-medium relative">71.4% success rate</div>
        </div>

        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex flex-col justify-center transition-all hover:shadow-md hover:-translate-y-1 cursor-pointer group">
          <div class="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-transparent rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div class="text-slate-500 font-semibold text-sm mb-3 flex items-center gap-2 uppercase tracking-wider relative">
             <span class="w-2.5 h-2.5 rounded-full bg-indigo-500"></span> GenAI Escalated
          </div>
          <div class="text-4xl font-extrabold text-slate-800 tracking-tight relative">2,145</div>
          <div class="text-sm text-slate-500 mt-3 font-medium relative">17.2% fallback rate</div>
        </div>

        <div class="bg-gradient-to-br from-rose-50 to-white p-6 rounded-2xl shadow-sm border border-rose-100 flex flex-col justify-center relative overflow-hidden transition-all hover:shadow-md hover:-translate-y-1 cursor-pointer">
          <div class="relative z-10">
            <div class="text-rose-600 font-semibold text-sm mb-3 flex items-center gap-2 uppercase tracking-wider">
               <span class="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse shadow-[0_0_8px_rgba(244,63,94,0.8)]"></span> Human Required
            </div>
            <div class="text-4xl font-extrabold text-rose-700 tracking-tight">1,411</div>
            <div class="text-sm text-rose-600 mt-3 font-medium flex items-center bg-rose-100/50 w-fit px-2 py-0.5 rounded-md">
              11.4% manual intervention
            </div>
          </div>
        </div>
      </div>

      <!-- Charts Section -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 col-span-2">
           <div class="flex justify-between items-center mb-6">
             <h3 class="text-lg font-bold text-slate-800 tracking-tight">System Performance Timeline</h3>
             <button class="p-2 hover:bg-slate-100 rounded-lg text-slate-400 transition-colors">
               <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z"></path></svg>
             </button>
           </div>
           <div echarts [options]="areaChart" class="h-[350px]"></div>
        </div>
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
           <div class="flex justify-between items-center mb-6">
             <h3 class="text-lg font-bold text-slate-800 tracking-tight">Resolution Breakdown</h3>
           </div>
           <div echarts [options]="pieChart" class="h-[350px]"></div>
        </div>
      </div>
    </div>
  `
})
export class DashboardComponent implements OnInit {
  areaChart = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(255, 255, 255, 0.95)', borderColor: '#e2e8f0', textStyle: { color: '#1e293b' }, padding: 12 },
    legend: { data: ['RAG Confidence', 'Response Time (ms)'], bottom: 0, icon: 'circle' },
    grid: { left: '3%', right: '4%', bottom: '12%', top: '5%', containLabel: true },
    xAxis: { 
      type: 'category', 
      boundaryGap: false, 
      data: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisLabel: { color: '#64748b' }
    },
    yAxis: [
      { 
        type: 'value', 
        name: 'Confidence (%)',
        splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } },
        axisLabel: { color: '#64748b' },
        nameTextStyle: { color: '#64748b', padding: [0, 0, 0, 20] }
      },
      { 
        type: 'value', 
        name: 'ms', 
        splitLine: { show: false },
        axisLabel: { color: '#64748b' },
        nameTextStyle: { color: '#64748b' }
      }
    ],
    series: [
      {
        name: 'RAG Confidence',
        type: 'line',
        smooth: 0.4,
        symbol: 'none',
        lineStyle: { width: 3, color: '#6366f1' },
        areaStyle: { 
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(99,102,241,0.3)' },
            { offset: 1, color: 'rgba(99,102,241,0.02)' }
          ])
        },
        data: [82, 85, 79, 88, 92, 89, 90]
      },
      {
        name: 'Response Time (ms)',
        type: 'line',
        smooth: 0.4,
        symbol: 'none',
        yAxisIndex: 1,
        lineStyle: { width: 3, color: '#fb923c', type: 'dashed' },
        data: [120, 132, 101, 134, 90, 110, 105]
      }
    ]
  };

  pieChart = {
    tooltip: { trigger: 'item', backgroundColor: 'rgba(255, 255, 255, 0.95)' },
    legend: { bottom: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: '#64748b' }, icon: 'circle' },
    series: [
      {
        name: 'Resolution',
        type: 'pie',
        radius: ['55%', '80%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 8,
          borderColor: '#fff',
          borderWidth: 4
        },
        label: { show: false },
        emphasis: {
          label: { show: true, fontSize: 24, fontWeight: 'bold', color: '#1e293b' }
        },
        labelLine: { show: false },
        data: [
          { value: 8902, name: 'RAG API', itemStyle: { color: '#10b981' } },
          { value: 2145, name: 'GenAI', itemStyle: { color: '#6366f1' } },
          { value: 1411, name: 'Agent', itemStyle: { color: '#f43f5e' } },
        ]
      }
    ]
  };

  ngOnInit() {}
}
