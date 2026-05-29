import { Component, OnInit, signal, ChangeDetectionStrategy, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AdminService } from '../../../core/services/admin.service';
import { SystemConfig } from '../../../shared/models';

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './admin.component.html'
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

  private destroyRef = inject(DestroyRef);

  constructor(private adminService: AdminService) {}

  ngOnInit(): void {
    this.loadConfig();
  }

  private loadConfig(): void {
    this.isLoading.set(true);
    this.adminService.getConfig().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
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

    this.adminService.updateConfig(current).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
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
