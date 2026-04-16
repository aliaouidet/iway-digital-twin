import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SystemConfig } from '../../shared/models';

@Injectable({ providedIn: 'root' })
export class AdminService {
  private readonly baseUrl = `${environment.apiUrl}/api/v1`;

  constructor(private http: HttpClient) {}

  getConfig(): Observable<SystemConfig> {
    return this.http.get<SystemConfig>(`${this.baseUrl}/admin/config`);
  }

  updateConfig(config: Partial<SystemConfig>): Observable<{ status: string; config: SystemConfig }> {
    return this.http.put<{ status: string; config: SystemConfig }>(`${this.baseUrl}/admin/config`, config);
  }
}
