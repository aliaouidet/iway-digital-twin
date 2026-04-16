import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import { LoginRequest, LoginResponse, User, UserRole } from '../../shared/models';

const TOKEN_KEY = 'iway_token';
const USER_KEY = 'iway_user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private userSubject = new BehaviorSubject<User | null>(this.getStoredUser());
  public user$ = this.userSubject.asObservable();

  constructor(private http: HttpClient) {}

  login(credentials: LoginRequest): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(
      `${environment.apiUrl}/auth/login`,
      credentials
    ).pipe(
      tap(response => {
        localStorage.setItem(TOKEN_KEY, response.access_token);
        localStorage.setItem(USER_KEY, JSON.stringify(response.user));
        this.userSubject.next(response.user);
      })
    );
  }

  logout(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    this.userSubject.next(null);
  }

  getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  }

  isLoggedIn(): boolean {
    return !!this.getToken();
  }

  getCurrentUser(): User | null {
    return this.userSubject.value;
  }

  getRole(): UserRole | null {
    return this.userSubject.value?.role || null;
  }

  hasRole(role: UserRole): boolean {
    return this.userSubject.value?.role === role;
  }

  /** Returns the default home route for the current user's role */
  getHomeRoute(): string {
    const role = this.getRole();
    switch (role) {
      case 'Adherent':
      case 'Prestataire':
        return '/chat';
      case 'Agent':
        return '/agent';
      case 'Admin':
        return '/admin';
      default:
        return '/login';
    }
  }

  private getStoredUser(): User | null {
    const raw = localStorage.getItem(USER_KEY);
    if (raw) {
      try { return JSON.parse(raw); } catch { return null; }
    }
    return null;
  }
}
