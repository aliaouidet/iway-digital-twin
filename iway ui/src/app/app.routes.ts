import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';
import { roleGuard } from './core/guards/role.guard';

export const routes: Routes = [
  { path: '', redirectTo: 'login', pathMatch: 'full' },
  {
    path: 'login',
    loadComponent: () => import('./features/login/components/login.component').then(m => m.LoginComponent)
  },

  // ZONE 1: User Chat (Adherent / Prestataire)
  {
    path: 'chat',
    canActivate: [authGuard, roleGuard(['Adherent', 'Prestataire'])],
    loadComponent: () => import('./zones/user-chat/user-chat.component').then(m => m.UserChatComponent)
  },

  // ZONE 2: HITL Agent Workspace
  {
    path: 'agent',
    canActivate: [authGuard, roleGuard(['Agent'])],
    loadComponent: () => import('./zones/agent/agent-workspace.component').then(m => m.AgentWorkspaceComponent)
  },

  // ZONE 3: Admin Dashboard
  {
    path: 'admin',
    canActivate: [authGuard, roleGuard(['Admin'])],
    loadComponent: () => import('./zones/admin/admin-layout.component').then(m => m.AdminLayoutComponent),
    children: [
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
        path: 'logs',
        loadComponent: () => import('./features/logs/components/logs.component').then(m => m.LogsComponent)
      },
      {
        path: 'insights',
        loadComponent: () => import('./features/insights/components/insights.component').then(m => m.InsightsComponent)
      },
      {
        path: 'config',
        loadComponent: () => import('./features/admin/components/admin.component').then(m => m.AdminComponent)
      },
    ]
  },

  { path: '**', redirectTo: 'login' }
];
