import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { DashboardMetrics } from '../../shared/models';

@Injectable({ providedIn: 'root' })
export class MetricsService {
  private readonly baseUrl = `${environment.apiUrl}/api/v1`;

  constructor(private http: HttpClient) {}

  getMetrics(startDate?: string, endDate?: string): Observable<DashboardMetrics> {
    let params = new HttpParams();
    if (startDate) params = params.set('start_date', startDate);
    if (endDate) params = params.set('end_date', endDate);
    return this.http.get<DashboardMetrics>(`${this.baseUrl}/metrics`, { params });
  }

  getHourlyTraffic(date?: string): Observable<{ hourly: { hour: number; label: string; count: number }[]; date: string }> {
    let params = new HttpParams();
    if (date) params = params.set('date', date);
    return this.http.get<any>(`${this.baseUrl}/metrics/traffic`, { params });
  }
}
