import { Component, OnInit, signal, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AdminService } from '../../../core/services/admin.service';
import { SystemConfig } from '../../../shared/models';

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-white tracking-tight" style="font-family: 'Figtree', sans-serif;">System Administration</h1>
          <p class="text-slate-500 mt-1 text-sm">Configure RAG engine, LLM parameters, and system behavior</p>
        </div>
        <button (click)="saveConfig()" [disabled]="isSaving()"
          class="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 rounded-xl text-xs font-semibold text-white transition-colors cursor-pointer flex items-center gap-1.5">
          <svg *ngIf="!isSaving()" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
          <svg *ngIf="isSaving()" class="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
          {{isSaving() ? 'Saving...' : 'Save Changes'}}
        </button>
      </div>

      <!-- Success Toast -->
      <div *ngIf="showSuccess()" class="px-4 py-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400 text-sm flex items-center gap-2">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
        Configuration saved successfully.
      </div>

      <!-- Loading -->
      <div *ngIf="isLoading()" class="space-y-6">
        <div *ngFor="let _ of [1,2,3]" class="bg-slate-800/50 rounded-2xl border border-slate-700/50 p-6 animate-pulse h-48"></div>
      </div>

      <!-- Tabs -->
      <div *ngIf="!isLoading() && config()" class="flex gap-2 border-b border-slate-800 pb-0">
        <button *ngFor="let tab of tabs" (click)="activeTab.set(tab.id)"
          [class]="activeTab() === tab.id
            ? 'px-5 py-3 text-sm font-semibold text-indigo-400 border-b-2 border-indigo-400 -mb-px cursor-pointer transition-all'
            : 'px-5 py-3 text-sm font-semibold text-slate-500 hover:text-slate-300 border-b-2 border-transparent -mb-px cursor-pointer transition-all'">
          {{tab.label}}
        </button>
      </div>

      <!-- RAG Config -->
      <div *ngIf="!isLoading() && config() && activeTab() === 'rag'" class="bg-[#0F172A] p-8 rounded-2xl border border-slate-800 space-y-8">
        <h3 class="text-base font-bold text-white" style="font-family: 'Figtree', sans-serif;">RAG Engine Settings</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div>
            <label class="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">Chunking Strategy</label>
            <select [(ngModel)]="config()!.rag.chunking_strategy"
              class="w-full px-4 py-3 bg-slate-800/50 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all cursor-pointer appearance-none">
              <option value="semantic">Semantic</option>
              <option value="fixed">Fixed Size</option>
              <option value="recursive">Recursive</option>
            </select>
          </div>
          <div>
            <label class="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">Top-K Results</label>
            <input [(ngModel)]="config()!.rag.top_k" type="number" min="1" max="10"
              class="w-full px-4 py-3 bg-slate-800/50 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all" />
          </div>
          <div>
            <label class="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">Similarity Threshold ({{config()!.rag.similarity_threshold}}%)</label>
            <input [(ngModel)]="config()!.rag.similarity_threshold" type="range" min="0" max="100" step="1"
              class="w-full accent-indigo-500 cursor-pointer" />
          </div>
          <div class="space-y-4">
            <div class="flex items-center justify-between">
              <label class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Enable AI Fallback</label>
              <label class="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" [(ngModel)]="config()!.rag.enable_ai_fallback" class="sr-only peer">
                <div class="w-10 h-5 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:bg-indigo-600 transition-colors after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-5"></div>
              </label>
            </div>
            <div class="flex items-center justify-between">
              <label class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Auto-Escalate Negative Sentiment</label>
              <label class="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" [(ngModel)]="config()!.rag.auto_escalate_negative_sentiment" class="sr-only peer">
                <div class="w-10 h-5 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:bg-indigo-600 transition-colors after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-5"></div>
              </label>
            </div>
          </div>
        </div>
      </div>

      <!-- LLM Config -->
      <div *ngIf="!isLoading() && config() && activeTab() === 'llm'" class="bg-[#0F172A] p-8 rounded-2xl border border-slate-800 space-y-8">
        <h3 class="text-base font-bold text-white" style="font-family: 'Figtree', sans-serif;">LLM Model Settings</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div>
            <label class="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">Primary Model</label>
            <select [(ngModel)]="config()!.llm.primary_model"
              class="w-full px-4 py-3 bg-slate-800/50 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all cursor-pointer appearance-none">
              <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
              <option value="gemini-2.5-pro">Gemini 2.5 Pro</option>
              <option value="qwen3.5:9b">Qwen 3.5 9B (Local)</option>
            </select>
          </div>
          <div>
            <label class="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">Temperature ({{config()!.llm.temperature}})</label>
            <input [(ngModel)]="config()!.llm.temperature" type="range" min="0" max="1" step="0.05"
              class="w-full accent-indigo-500 cursor-pointer" />
          </div>
          <div class="md:col-span-2">
            <label class="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">System Prompt</label>
            <textarea [(ngModel)]="config()!.llm.system_prompt" rows="4"
              class="w-full px-4 py-3 bg-slate-800/50 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all resize-none font-mono"></textarea>
          </div>
        </div>
      </div>

      <!-- Retry Config -->
      <div *ngIf="!isLoading() && config() && activeTab() === 'retry'" class="bg-[#0F172A] p-8 rounded-2xl border border-slate-800 space-y-8">
        <h3 class="text-base font-bold text-white" style="font-family: 'Figtree', sans-serif;">Error Handling & Retry</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div>
            <label class="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">Max Retries</label>
            <input [(ngModel)]="config()!.retry.max_retries" type="number" min="0" max="10"
              class="w-full px-4 py-3 bg-slate-800/50 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all" />
          </div>
          <div>
            <label class="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">Backoff Delay (seconds)</label>
            <input [(ngModel)]="config()!.retry.backoff_seconds" type="number" min="1" max="30"
              class="w-full px-4 py-3 bg-slate-800/50 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all" />
          </div>
        </div>
      </div>
    </div>
  `
})
export class AdminComponent implements OnInit {
  config = signal<SystemConfig | null>(null);
  isLoading = signal(true);
  isSaving = signal(false);
  showSuccess = signal(false);
  activeTab = signal('rag');

  tabs = [
    { id: 'rag', label: 'RAG Engine' },
    { id: 'llm', label: 'LLM Settings' },
    { id: 'retry', label: 'Error Handling' },
  ];

  constructor(private adminService: AdminService) {}

  ngOnInit(): void {
    this.loadConfig();
  }

  private loadConfig(): void {
    this.isLoading.set(true);
    this.adminService.getConfig().subscribe({
      next: (data) => {
        this.config.set({ ...data });
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false)
    });
  }

  saveConfig(): void {
    const current = this.config();
    if (!current) return;

    this.isSaving.set(true);
    this.showSuccess.set(false);

    this.adminService.updateConfig(current).subscribe({
      next: (resp) => {
        this.config.set(resp.config);
        this.isSaving.set(false);
        this.showSuccess.set(true);
        setTimeout(() => this.showSuccess.set(false), 3000);
      },
      error: () => this.isSaving.set(false)
    });
  }
}
