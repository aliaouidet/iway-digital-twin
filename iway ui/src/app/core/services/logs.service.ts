import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { LogFilter, PaginatedLogs } from '../../shared/models';

@Injectable({ providedIn: 'root' })
export class LogsService {
  private readonly baseUrl = `${environment.apiUrl}/api/v1`;

  constructor(private http: HttpClient) {}

  getLogs(filter: LogFilter = {}): Observable<PaginatedLogs> {
    let params = new HttpParams();
    if (filter.page) params = params.set('page', filter.page.toString());
    if (filter.page_size) params = params.set('page_size', filter.page_size.toString());
    if (filter.outcome) params = params.set('outcome', filter.outcome);
    if (filter.user_id) params = params.set('user_id', filter.user_id);
    if (filter.search) params = params.set('search', filter.search);
    if (filter.min_similarity !== undefined) {
      params = params.set('min_similarity', (filter.min_similarity / 100).toString());
    }

    return this.http.get<PaginatedLogs>(`${this.baseUrl}/logs`, { params });
  }
}
