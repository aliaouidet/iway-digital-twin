import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { UserRole } from '../../shared/models';

export function roleGuard(allowedRoles: UserRole[]): CanActivateFn {
  return () => {
    const authService = inject(AuthService);
    const router = inject(Router);

    if (!authService.isLoggedIn()) {
      return router.createUrlTree(['/login']);
    }

    const role = authService.getRole();
    if (role && allowedRoles.includes(role)) {
      return true;
    }

    // Redirect to the user's own zone
    const redirectMap: Record<string, string> = {
      'Adherent': '/chat',
      'Prestataire': '/chat',
      'Agent': '/agent',
      'Admin': '/admin',
    };
    return router.createUrlTree([redirectMap[role || ''] || '/login']);
  };
}
