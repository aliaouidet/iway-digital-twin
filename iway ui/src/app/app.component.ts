import { Component, OnInit, OnDestroy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { ToastComponent } from './shared/components/toast.component';
import { Subscription } from 'rxjs';
import { AuthService } from './core/services/auth.service';
import { ThemeService } from './core/services/theme.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, ToastComponent],
  template: `<router-outlet></router-outlet><app-toast></app-toast>`
})
export class AppComponent implements OnInit, OnDestroy {
  private authSub?: Subscription;

  constructor(
    private authService: AuthService,
    private themeService: ThemeService
  ) {}

  ngOnInit(): void {
    // Theme is auto-applied by ThemeService effect on startup
  }

  ngOnDestroy(): void {
    this.authSub?.unsubscribe();
  }
}
