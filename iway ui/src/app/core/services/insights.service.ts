import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { InsightsData } from '../../shared/models';

@Injectable({ providedIn: 'root' })
export class InsightsService {
  private readonly baseUrl = `${environment.apiUrl}/api/v1`;

  constructor(private http: HttpClient) {}

  getInsights(): Observable<InsightsData> {
    return this.http.get<InsightsData>(`${this.baseUrl}/insights`);
  }
}
