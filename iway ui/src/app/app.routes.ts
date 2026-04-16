import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  { 
    path: 'dashboard', 
    loadComponent: () => import('./features/dashboard/components/dashboard.component').then(m => m.DashboardComponent)
  },
  { 
    path: 'tickets', 
    loadComponent: () => import('./features/tickets/components/tickets.component').then(m => m.TicketsComponent)
  },
  { 
    path: 'chat', 
    loadComponent: () => import('./features/chat/components/chat.component').then(m => m.ChatComponent)
  },
  { 
    path: 'logs', 
    loadComponent: () => import('./features/logs/components/logs.component').then(m => m.LogsComponent)
  },
  { 
    path: 'insights', 
    loadComponent: () => import('./features/insights/components/insights.component').then(m => m.InsightsComponent)
  },
  { 
    path: 'admin', 
    loadComponent: () => import('./features/admin/components/admin.component').then(m => m.AdminComponent)
  }
];
