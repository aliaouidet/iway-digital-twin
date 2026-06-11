import { Injectable, OnDestroy, signal } from '@angular/core';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { Observable, Subject, Subscription, EMPTY, timer, defer, throwError } from 'rxjs';
import { catchError, filter, map, retry, takeUntil } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';
import { RealtimeMetricUpdate } from '../../shared/models';
import { QueueItem } from '../../shared/models/chat.interface';

export interface WsMessage {
  type: string;
  payload: any;
}

@Injectable({ providedIn: 'root' })
export class WebSocketService implements OnDestroy {
  private socket$: WebSocketSubject<WsMessage> | null = null;
  private destroy$ = new Subject<void>();
  private messages$ = new Subject<WsMessage>();
  private pingSub: Subscription | null = null;
  private authExpired = false;
  private _sidebarQueue = signal<QueueItem[]>([]);
  public sidebarQueue = this._sidebarQueue.asReadonly();

  constructor(private authService: AuthService) {}

  /** Built fresh per connection attempt so retries pick up a re-issued token. */
  private createSocket(fallbackToken?: string): WebSocketSubject<WsMessage> {
    const token = this.authService.getToken() || fallbackToken;
    // Token travels in the FIRST frame, not the URL — query strings leak into
    // proxy logs and browser history.
    const socket: WebSocketSubject<WsMessage> = webSocket<WsMessage>({
      url: environment.wsUrl,
      openObserver: {
        next: () => {
          if (token) {
            socket.next({ type: 'auth', token } as unknown as WsMessage);
          }
        }
      },
      closeObserver: {
        next: (event: CloseEvent) => {
          console.log('[WebSocket] Connection closed', event.code);
          // 4001/4003 = token rejected — retrying with it is pointless. The
          // next REST call will 401 and the interceptor handles the redirect.
          if (event.code === 4001 || event.code === 4003) {
            this.authExpired = true;
          }
        }
      }
    });
    this.socket$ = socket;
    return socket;
  }

  connect(token?: string): void {
    if (this.socket$ && !this.socket$.closed) {
      return;
    }
    this.authExpired = false;

    defer(() => this.createSocket(token)).pipe(
      retry({ count: 10, delay: (error, retryCount) => {
        if (this.authExpired) {
          return throwError(() => new Error('auth_expired'));
        }
        const delayMs = Math.min(1000 * Math.pow(2, retryCount), 30000);
        console.log(`[WebSocket] Reconnecting in ${delayMs}ms (attempt ${retryCount})...`);
        return timer(delayMs);
      }}),
      catchError(err => {
        console.error('[WebSocket] Fatal error:', err);
        this.socket$ = null;   // a later connect() can re-establish
        return EMPTY;
      }),
      takeUntil(this.destroy$)
    ).subscribe({
      next: (msg) => {
        this.messages$.next(msg);
        this.handleSidebarUpdates(msg);
      },
      error: (err) => console.error('[WebSocket] Stream error:', err),
      complete: () => { this.socket$ = null; },
    });

    // Send periodic pings — one timer per connection (cleared in disconnect()),
    // otherwise each connect() after a disconnect() leaks an extra interval.
    this.pingSub?.unsubscribe();
    this.pingSub = timer(30000, 30000).pipe(
      takeUntil(this.destroy$)
    ).subscribe(() => this.sendMessage({ type: 'PING', payload: null }));
  }

  disconnect(): void {
    this.pingSub?.unsubscribe();
    this.pingSub = null;
    if (this.socket$) {
      this.socket$.complete();
      this.socket$ = null;
    }
  }

  setInitialQueue(items: QueueItem[]): void {
    this._sidebarQueue.set(items);
  }

  private handleSidebarUpdates(msg: WsMessage): void {
    // Listen for sidebar_update or related escalation events to prepend/update the queue
    if (msg.type === 'sidebar_update' || msg.type === 'NEW_ESCALATION' || msg.type === 'SESSION_UPDATED') {
      const payload = msg.payload || {};
      const newItem: QueueItem = {
        ...payload,
        id: payload.id || payload.session_id,
        status: payload.status || (msg.type === 'NEW_ESCALATION' ? 'handoff_pending' : 'active'),
        message_count: payload.message_count || 0,
        last_message: payload.last_message || '',
        agent_matricule: payload.agent_matricule || null,
        user_matricule: payload.user_matricule || '',
      };
      
      if (!newItem.id) return;
      
      this._sidebarQueue.update(queue => {
        const index = queue.findIndex(item => item.id === newItem.id);
        if (index > -1) {
          // If it exists, update it
          const updatedQueue = [...queue];
          updatedQueue[index] = { ...updatedQueue[index], ...newItem };
          return updatedQueue;
        } else {
          // If it does not exist, prepend it immediately
          return [newItem, ...queue];
        }
      });
    } else if (msg.type === 'SESSION_RESOLVED') {
      // Remove resolved sessions from queue
      const resolvedId = msg.payload?.id || msg.payload?.session_id;
      if (resolvedId) {
        this._sidebarQueue.update(queue => queue.filter(item => item.id !== resolvedId));
      }
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
