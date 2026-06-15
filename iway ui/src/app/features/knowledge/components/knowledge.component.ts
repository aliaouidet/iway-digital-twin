import { Component, OnInit, signal, computed, ChangeDetectionStrategy, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { ToastService } from '../../../core/services/toast.service';
import { ErrorBannerComponent } from '../../../shared/components/error-banner.component';

interface KbUsage { retrieved: number; helpful: number; unhelpful: number; helpfulness: number | null; boost: number; }
interface KbEntry {
  id: string; source_id: string; question: string; answer: string;
  tags: string[]; origin: string; status: string; agent_name: string | null;
  created_at: string | null; updated_at: string | null; conflicts_with: string | null;
  usage?: KbUsage;
}
interface Correction {
  id?: string; session_id: string; correct_answer: string;
  correction_type: string; agent_name?: string; created_at: string;
}

@Component({
  selector: 'app-knowledge',
  standalone: true,
  imports: [CommonModule, FormsModule, ErrorBannerComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="space-y-6">
      <div class="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 dark:text-white tracking-tight" style="font-family: 'Figtree', sans-serif;">Knowledge Base</h1>
          <p class="text-slate-500 dark:text-slate-400 mt-1 text-sm">Curate agent-validated knowledge — the continuous-learning flywheel</p>
        </div>
        <button (click)="reload()" class="px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-semibold text-slate-700 dark:text-slate-300 transition-colors cursor-pointer">Refresh</button>
      </div>

      <!-- Tabs -->
      <div class="flex gap-1 bg-slate-100 dark:bg-slate-800/50 p-1 rounded-xl border border-slate-200 dark:border-slate-700/50 w-fit">
        <button *ngFor="let t of [['entries','Entries'],['corrections','Corrections']]" (click)="tab.set(t[0])"
          [class]="tab() === t[0]
            ? 'px-4 py-1.5 bg-indigo-600 shadow-sm rounded-lg text-[11px] font-semibold text-white cursor-pointer'
            : 'px-4 py-1.5 rounded-lg text-[11px] font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 cursor-pointer'">
          {{t[1]}}
        </button>
      </div>

      <!-- KB-health strip -->
      <div *ngIf="tab() === 'entries' && !loading()" class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="bg-white dark:bg-[#0F172A] rounded-xl border border-slate-200 dark:border-slate-800 p-3 shadow-sm dark:shadow-none">
          <div class="text-[10px] uppercase tracking-wider text-slate-500">Entries</div>
          <div class="text-xl font-extrabold text-slate-800 dark:text-white">{{health().total}}</div>
        </div>
        <div class="bg-white dark:bg-[#0F172A] rounded-xl border border-slate-200 dark:border-slate-800 p-3 shadow-sm dark:shadow-none">
          <div class="text-[10px] uppercase tracking-wider text-slate-500">Active</div>
          <div class="text-xl font-extrabold text-emerald-600 dark:text-emerald-400">{{health().active}}</div>
        </div>
        <div class="bg-white dark:bg-[#0F172A] rounded-xl border p-3 shadow-sm dark:shadow-none"
          [class]="health().conflict > 0 ? 'border-amber-300 dark:border-amber-500/40' : 'border-slate-200 dark:border-slate-800'">
          <div class="text-[10px] uppercase tracking-wider text-slate-500">Conflicts</div>
          <div class="text-xl font-extrabold" [class]="health().conflict > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-slate-800 dark:text-white'">{{health().conflict}}</div>
        </div>
        <div class="bg-white dark:bg-[#0F172A] rounded-xl border border-slate-200 dark:border-slate-800 p-3 shadow-sm dark:shadow-none">
          <div class="text-[10px] uppercase tracking-wider text-slate-500">Avg helpfulness</div>
          <div class="text-xl font-extrabold text-slate-800 dark:text-white">{{ health().avgHelp === null ? '—' : health().avgHelp + '%' }}</div>
        </div>
      </div>

      <app-error-banner *ngIf="error()" [message]="error()!" (retry)="reload()"></app-error-banner>

      <!-- ENTRIES TAB -->
      <ng-container *ngIf="tab() === 'entries'">
        <!-- Status filter -->
        <div class="flex flex-wrap gap-1.5">
          <button *ngFor="let s of statusFilters" (click)="statusFilter.set(s.value)"
            [class]="statusFilter() === s.value
              ? 'px-3 py-1 rounded-lg text-[11px] font-semibold bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900 cursor-pointer'
              : 'px-3 py-1 rounded-lg text-[11px] font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer'">
            {{s.label}} <span class="opacity-60">{{countFor(s.value)}}</span>
          </button>
        </div>

        <div *ngIf="loading()" class="space-y-2">
          <div *ngFor="let _ of [1,2,3,4,5]" class="h-16 rounded-xl bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
        </div>

        <div *ngIf="!loading() && filteredEntries().length === 0" class="text-center py-14">
          <svg class="w-10 h-10 mx-auto mb-3 text-slate-300 dark:text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"/></svg>
          <p class="text-sm font-semibold text-slate-500 dark:text-slate-400">No knowledge entries</p>
          <p class="text-xs text-slate-400 dark:text-slate-600 mt-1">Agent-validated Q&amp;A from resolved sessions appears here.</p>
        </div>

        <div *ngIf="!loading() && filteredEntries().length > 0" class="space-y-2.5">
          <div *ngFor="let e of filteredEntries()" class="bg-white dark:bg-[#0F172A] rounded-xl border p-4 shadow-sm dark:shadow-none"
            [class]="e.status === 'conflict' ? 'border-amber-300 dark:border-amber-500/40' : 'border-slate-200 dark:border-slate-800'">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 flex-wrap mb-1">
                  <span class="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase" [class]="statusClass(e.status)">{{e.status}}</span>
                  <span class="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400">{{e.origin}}</span>
                  <span *ngFor="let t of e.tags" class="px-1.5 py-0.5 rounded text-[10px] bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-300">{{t}}</span>
                </div>
                <p class="text-sm font-semibold text-slate-800 dark:text-white truncate">{{e.question}}</p>
                <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2">{{e.answer}}</p>
                <div class="flex items-center gap-3 text-[10px] text-slate-400 dark:text-slate-600 mt-2 flex-wrap">
                  <span *ngIf="e.agent_name">by {{e.agent_name}}</span>
                  <span *ngIf="e.created_at">{{e.created_at | date:'dd MMM yyyy'}}</span>
                  <span *ngIf="e.usage" title="Times retrieved for an answer">↺ {{e.usage.retrieved}} used</span>
                  <span *ngIf="e.usage" title="Feedback-weighted retrieval boost">boost ×{{e.usage.boost}}</span>
                  <span *ngIf="e.usage && e.usage.helpfulness !== null"
                    [class]="e.usage.helpfulness >= 0.5 ? 'text-emerald-500' : 'text-rose-500'">
                    {{(e.usage.helpfulness * 100).toFixed(0)}}% helpful
                  </span>
                </div>
              </div>
              <div class="flex items-center gap-1.5 flex-shrink-0">
                <ng-container *ngIf="e.status === 'conflict'">
                  <button (click)="resolveConflict(e, 'accept')" class="px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-emerald-600 hover:bg-emerald-500 text-white cursor-pointer">Accept</button>
                  <button (click)="resolveConflict(e, 'reject')" class="px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-rose-600 hover:bg-rose-500 text-white cursor-pointer">Reject</button>
                </ng-container>
                <button (click)="openEdit(e)" title="Edit" class="w-7 h-7 flex items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-indigo-500 cursor-pointer">
                  <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z"/></svg>
                </button>
                <button *ngIf="e.status !== 'retired'" (click)="setStatus(e, 'retire')" title="Retire" class="w-7 h-7 flex items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-amber-500 cursor-pointer">
                  <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"/></svg>
                </button>
                <button *ngIf="e.status === 'retired'" (click)="setStatus(e, 'restore')" title="Restore" class="w-7 h-7 flex items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-emerald-500 cursor-pointer">
                  <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                </button>
                <button (click)="remove(e)" title="Delete" class="w-7 h-7 flex items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-rose-500 cursor-pointer">
                  <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </ng-container>

      <!-- CORRECTIONS TAB -->
      <ng-container *ngIf="tab() === 'corrections'">
        <div *ngIf="loadingCorr()" class="space-y-2">
          <div *ngFor="let _ of [1,2,3]" class="h-16 rounded-xl bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
        </div>
        <div *ngIf="!loadingCorr() && corrections().length === 0" class="text-center py-14">
          <p class="text-sm font-semibold text-slate-500 dark:text-slate-400">No corrections flagged</p>
          <p class="text-xs text-slate-400 dark:text-slate-600 mt-1">Agent-flagged AI errors are recorded here and re-embedded as authoritative answers.</p>
        </div>
        <div *ngIf="!loadingCorr()" class="space-y-2.5">
          <div *ngFor="let c of corrections()" class="bg-white dark:bg-[#0F172A] rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm dark:shadow-none">
            <div class="flex items-center gap-2 mb-1">
              <span class="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-rose-50 text-rose-600 dark:bg-rose-500/10 dark:text-rose-400">{{c.correction_type}}</span>
              <span *ngIf="c.agent_name" class="text-[10px] text-slate-400">by {{c.agent_name}}</span>
              <span class="text-[10px] text-slate-400 ml-auto">{{c.created_at | date:'dd MMM, HH:mm'}}</span>
            </div>
            <p class="text-xs text-slate-600 dark:text-slate-300"><span class="text-emerald-600 dark:text-emerald-400 font-semibold">Correct answer:</span> {{c.correct_answer}}</p>
          </div>
        </div>
      </ng-container>

      <!-- EDIT MODAL -->
      <div *ngIf="editing() as e" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" (click)="editing.set(null)">
        <div class="bg-white dark:bg-[#0F172A] rounded-2xl border border-slate-200 dark:border-slate-800 p-6 w-full max-w-lg shadow-xl" (click)="$event.stopPropagation()">
          <h3 class="text-base font-bold text-slate-900 dark:text-white mb-4">Edit knowledge entry</h3>
          <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Question</label>
          <input [(ngModel)]="editQuestion" class="w-full mt-1 mb-3 px-3 py-2 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-xl text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/40" />
          <label class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Answer</label>
          <textarea [(ngModel)]="editAnswer" rows="5" class="w-full mt-1 mb-4 px-3 py-2 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-xl text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/40 resize-none"></textarea>
          <div class="flex justify-end gap-2">
            <button (click)="editing.set(null)" class="px-4 py-2 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 cursor-pointer">Cancel</button>
            <button (click)="saveEdit()" [disabled]="saving() || !editQuestion.trim() || !editAnswer.trim()" class="px-4 py-2 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white cursor-pointer">{{ saving() ? 'Saving…' : 'Save & re-embed' }}</button>
          </div>
        </div>
      </div>
    </div>
  `
})
export class KnowledgeComponent implements OnInit {
  private http = inject(HttpClient);
  private toast = inject(ToastService);
  private destroyRef = inject(DestroyRef);
  private readonly base = `${environment.apiUrl}/api/v1/knowledge`;

  tab = signal<string>('entries');
  entries = signal<KbEntry[]>([]);
  corrections = signal<Correction[]>([]);
  loading = signal(true);
  loadingCorr = signal(false);
  error = signal<string | null>(null);
  saving = signal(false);
  editing = signal<KbEntry | null>(null);
  statusFilter = signal<string>('all');

  editQuestion = '';
  editAnswer = '';

  statusFilters = [
    { value: 'all', label: 'All' },
    { value: 'active', label: 'Active' },
    { value: 'conflict', label: 'Conflicts' },
    { value: 'needs_review', label: 'Needs review' },
    { value: 'retired', label: 'Retired' },
  ];

  filteredEntries = computed(() => {
    const f = this.statusFilter();
    const all = this.entries();
    return f === 'all' ? all : all.filter(e => e.status === f);
  });

  health = computed(() => {
    const all = this.entries();
    const by = (s: string) => all.filter(e => e.status === s).length;
    const withHelp = all.filter(e => e.usage && e.usage.helpfulness !== null);
    const avgHelp = withHelp.length
      ? Math.round(withHelp.reduce((a, e) => a + (e.usage!.helpfulness! * 100), 0) / withHelp.length)
      : null;
    return { total: all.length, active: by('active'), conflict: by('conflict'), retired: by('retired'), avgHelp };
  });

  ngOnInit(): void {
    this.loadEntries();
    this.loadCorrections();
  }

  reload(): void {
    if (this.tab() === 'entries') this.loadEntries();
    else this.loadCorrections();
  }

  countFor(status: string): number {
    const all = this.entries();
    return status === 'all' ? all.length : all.filter(e => e.status === status).length;
  }

  loadEntries(): void {
    this.loading.set(true);
    this.error.set(null);
    this.http.get<{ entries: KbEntry[] }>(`${this.base}/entries`)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => { this.entries.set(res.entries || []); this.loading.set(false); },
        error: () => { this.error.set('Failed to load knowledge entries.'); this.loading.set(false); },
      });
  }

  loadCorrections(): void {
    this.loadingCorr.set(true);
    this.http.get<{ corrections: Correction[] }>(`${environment.apiUrl}/api/v1/corrections`)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => { this.corrections.set(res.corrections || []); this.loadingCorr.set(false); },
        error: () => { this.loadingCorr.set(false); },
      });
  }

  openEdit(e: KbEntry): void {
    this.editing.set(e);
    this.editQuestion = e.question || '';
    this.editAnswer = e.answer || '';
  }

  saveEdit(): void {
    const e = this.editing();
    if (!e || this.saving()) return;
    this.saving.set(true);
    this.http.put(`${this.base}/entries/${e.id}`, { question: this.editQuestion.trim(), answer: this.editAnswer.trim() })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => { this.saving.set(false); this.editing.set(null); this.toast.show('Entry updated & re-embedded.', 'success'); this.loadEntries(); },
        error: () => { this.saving.set(false); this.toast.show('Update failed.', 'error'); },
      });
  }

  setStatus(e: KbEntry, action: 'retire' | 'restore'): void {
    this.http.post(`${this.base}/entries/${e.id}/${action}`, {})
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => { this.toast.show(`Entry ${action === 'retire' ? 'retired' : 'restored'}.`, 'success'); this.loadEntries(); },
        error: () => this.toast.show('Action failed.', 'error'),
      });
  }

  remove(e: KbEntry): void {
    if (!confirm('Delete this knowledge entry permanently?')) return;
    this.http.delete(`${this.base}/entries/${e.id}`)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => { this.toast.show('Entry deleted.', 'success'); this.loadEntries(); },
        error: () => this.toast.show('Delete failed.', 'error'),
      });
  }

  resolveConflict(e: KbEntry, action: 'accept' | 'reject'): void {
    this.http.post(`${this.base}/entries/${e.id}/resolve-conflict`, { action })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => { this.toast.show(`Conflict ${action}ed.`, 'success'); this.loadEntries(); },
        error: () => this.toast.show('Resolution failed.', 'error'),
      });
  }

  statusClass(status: string): string {
    const map: Record<string, string> = {
      active: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400',
      conflict: 'bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400',
      needs_review: 'bg-orange-50 text-orange-600 dark:bg-orange-500/10 dark:text-orange-400',
      retired: 'bg-slate-100 text-slate-500 dark:bg-slate-700/40 dark:text-slate-400',
      superseded: 'bg-slate-100 text-slate-500 dark:bg-slate-700/40 dark:text-slate-400',
    };
    return map[status] || map['active'];
  }
}
