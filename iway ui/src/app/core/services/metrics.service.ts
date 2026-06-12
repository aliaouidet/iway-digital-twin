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

  /** AI-Ops snapshot: LLM tokens, cache hit rate, escalation paths,
   *  graph-node latencies, circuit breakers, persistence health. */
  getOpsMetrics(): Observable<OpsMetrics> {
    return this.http.get<OpsMetrics>(`${this.baseUrl}/monitoring/ops`);
  }
}

export interface OpsMetrics {
  tokens: {
    total_tokens: number;
    tokens_24h: number;
    llm_requests: number;
    avg_tokens_per_llm_request: number;
  };
  cache: { hits: number; misses: number; hit_rate: number };
  escalations: { [path: string]: number };
  nodes: { node: string; avg_ms: number; calls: number }[];
  circuits: { [name: string]: { name: string; state: string; total_failures: number } };
  persistence: { total_failures: number; consecutive_failures: number; degraded: boolean; last_error: string | null };
}
