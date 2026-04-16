import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { EscalationTicket, Reclamation, ReclamationInput } from '../../shared/models';

@Injectable({ providedIn: 'root' })
export class TicketService {
  private readonly baseUrl = `${environment.apiUrl}/api/v1`;

  constructor(private http: HttpClient) {}

  getEscalationTickets(): Observable<EscalationTicket[]> {
    return this.http.get<EscalationTicket[]>(`${this.baseUrl}/dashboard/tickets`);
  }

  getReclamations(): Observable<Reclamation[]> {
    return this.http.get<Reclamation[]>(`${this.baseUrl}/reclamations`);
  }

  createReclamation(data: ReclamationInput): Observable<{ status: string; ticket: Reclamation }> {
    return this.http.post<{ status: string; ticket: Reclamation }>(`${this.baseUrl}/reclamations`, data);
  }

  escalate(data: {
    matricule: string;
    chat_history: Array<{ role: string; content: string }>;
    reason: string;
  }): Observable<{ status: string; case_id: string; queue_position: number; estimated_wait: string }> {
    return this.http.post<any>(`${this.baseUrl}/support/escalade`, data);
  }
}
