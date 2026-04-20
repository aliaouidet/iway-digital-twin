import { Injectable, OnDestroy } from '@angular/core';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { Observable, Subject, EMPTY, timer } from 'rxjs';
import { catchError, filter, map, retry, share, switchMap, takeUntil } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { RealtimeMetricUpdate } from '../../shared/models';

export interface WsMessage {
  type: string;
  payload: any;
}

@Injectable({ providedIn: 'root' })
export class WebSocketService implements OnDestroy {
  private socket$: WebSocketSubject<WsMessage> | null = null;
  private destroy$ = new Subject<void>();
  private messages$ = new Subject<WsMessage>();

  connect(): void {
    if (this.socket$ && !this.socket$.closed) {
      return;
    }

    this.socket$ = webSocket<WsMessage>({
      url: environment.wsUrl,
      openObserver: {
        next: () => console.log('[WebSocket] Connected to', environment.wsUrl)
      },
      closeObserver: {
        next: () => console.log('[WebSocket] Connection closed')
      }
    });

    this.socket$.pipe(
      retry({ count: 10, delay: (error, retryCount) => {
        const delayMs = Math.min(1000 * Math.pow(2, retryCount), 30000);
        console.log(`[WebSocket] Reconnecting in ${delayMs}ms (attempt ${retryCount})...`);
        return timer(delayMs);
      }}),
      catchError(err => {
        console.error('[WebSocket] Fatal error:', err);
        return EMPTY;
      }),
      takeUntil(this.destroy$)
    ).subscribe({
      next: (msg) => this.messages$.next(msg),
      error: (err) => console.error('[WebSocket] Stream error:', err),
    });

    // Send periodic pings
    timer(30000, 30000).pipe(
      takeUntil(this.destroy$)
    ).subscribe(() => this.sendMessage({ type: 'PING', payload: null }));
  }

  disconnect(): void {
    if (this.socket$) {
      this.socket$.complete();
      this.socket$ = null;
    }
  }

  getMessages(): Observable<WsMessage> {
    return this.messages$.asObservable();
  }

  getMetricUpdates(): Observable<RealtimeMetricUpdate> {
    return this.messages$.pipe(
      filter(msg => msg.type === 'METRIC_UPDATE'),
      map(msg => msg.payload as RealtimeMetricUpdate)
    );
  }

  getTicketUpdates(): Observable<any> {
    return this.messages$.pipe(
      filter(msg => msg.type === 'TICKET_UPDATE'),
      map(msg => msg.payload)
    );
  }

  getEscalationUpdates(): Observable<any> {
    return this.messages$.pipe(
      filter(msg => msg.type === 'NEW_ESCALATION'),
      map(msg => msg.payload)
    );
  }

  getSessionUpdates(): Observable<any> {
    return this.messages$.pipe(
      filter(msg => ['NEW_SESSION', 'AGENT_JOINED', 'SESSION_RESOLVED'].includes(msg.type)),
      map(msg => ({ type: msg.type, ...msg.payload }))
    );
  }

  getTraceUpdates(): Observable<any> {
    return this.messages$.pipe(
      filter(msg => msg.type === 'NEW_TRACE'),
      map(msg => msg.payload)
    );
  }

  sendMessage(msg: WsMessage): void {
    if (this.socket$ && !this.socket$.closed) {
      this.socket$.next(msg);
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    this.disconnect();
  }
}
