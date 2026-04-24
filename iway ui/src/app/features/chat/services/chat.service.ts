import { Injectable, OnDestroy } from '@angular/core';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { Subject, EMPTY, timer, Subscription } from 'rxjs';
import { catchError, retry, takeUntil } from 'rxjs/operators';
import { environment } from '../../../../environments/environment';
import { AuthService } from '../../../core/services/auth.service';

export interface ChatEvent {
  type: string;
  [key: string]: any;
}

@Injectable({
  providedIn: 'root'
})
export class ChatService implements OnDestroy {
  private socket$: WebSocketSubject<any> | null = null;
  private destroy$ = new Subject<void>();
  private pingSubscription: Subscription | null = null;

  // --- Connection state ---
  private connected = false;
  private sessionId: string | null = null;
  private messageQueue: { type: string; content: string }[] = [];

  // --- Event subjects ---
  private historySubject = new Subject<any[]>();
  private tokenSubject = new Subject<string>();
  private thinkingSubject = new Subject<{status: string, node: string}>();
  private doneSubject = new Subject<{confidence?: number, source?: string}>();
  private handoffSubject = new Subject<{reason: string}>();
  private errorSubject = new Subject<string>();
  private connectedSubject = new Subject<{role: string, session_id: string}>();

  history$ = this.historySubject.asObservable();
  token$ = this.tokenSubject.asObservable();
  thinking$ = this.thinkingSubject.asObservable();
  done$ = this.doneSubject.asObservable();
  handoff$ = this.handoffSubject.asObservable();
  error$ = this.errorSubject.asObservable();
  connected$ = this.connectedSubject.asObservable();

  constructor(private authService: AuthService) {}

  connect(sessionId: string): void {
    // Guard: don't connect without a valid auth token
    const token = this.authService.getToken();
    if (!token) {
      console.error('[Chat WS] Cannot connect: No auth token available');
      this.errorSubject.next('Authentication required. Please log in.');
      return;
    }

    // Clean up any existing connection
    if (this.socket$ && !this.socket$.closed) {
      this.socket$.complete();
    }
    this.stopPing();
    this.connected = false;
    this.sessionId = sessionId;

    const wsUrl = `${environment.apiUrl.replace('http', 'ws')}/ws/chat/${sessionId}?token=${token}`;

    this.socket$ = webSocket({
      url: wsUrl,
      openObserver: {
        next: () => {
          console.log('[Chat WS] Connected to session', sessionId);
          // Send user_connect handshake immediately on open
          this.sendRaw({ type: 'user_connect' });
          // Start heartbeat ping cycle
          this.startPing();
        }
      },
      closeObserver: {
        next: (event) => {
          console.log('[Chat WS] Connection closed', event);
          this.connected = false;
          this.stopPing();
        }
      }
    });

    this.socket$.pipe(
      retry({
        count: 5,
        delay: (error, retryCount) => {
          const delayMs = Math.min(2000 * Math.pow(2, retryCount - 1), 30000);
          console.log(`[Chat WS] Reconnecting in ${delayMs}ms (attempt ${retryCount})...`);
          return timer(delayMs);
        },
        resetOnSuccess: true,
      }),
      catchError(err => {
        console.error('[Chat WS] Fatal error:', err);
        this.errorSubject.next('Connection lost. Please refresh the page.');
        return EMPTY;
      }),
      takeUntil(this.destroy$)
    ).subscribe({
      next: (msg: ChatEvent) => this.handleMessage(msg),
      error: (err) => console.error('[Chat WS] Stream error:', err)
    });
  }

  private handleMessage(msg: ChatEvent): void {
    switch (msg.type) {
      case 'connected':
        // Backend confirmed our user_connect handshake
        this.connected = true;
        this.connectedSubject.next({ role: msg['role'], session_id: msg['session_id'] });
        console.log('[Chat WS] Session bound as', msg['role']);
        // Flush any messages queued while disconnected
        this.flushMessageQueue();
        break;
      case 'history':
        this.historySubject.next(msg['messages'] || []);
        break;
      case 'ai_token':
        this.tokenSubject.next(msg['token']);
        break;
      case 'thinking':
        this.thinkingSubject.next({
          status: msg['status'] || 'Processing...',
          node: msg['node'] || 'unknown'
        });
        break;
      case 'ai_done':
        this.doneSubject.next({ confidence: msg['confidence'], source: msg['source'] });
        break;
      case 'handoff_started':
        this.handoffSubject.next({ reason: msg['reason'] || 'Transferring to agent...' });
        break;
      case 'agent_message':
        // Agent sent a message — treat as assistant message via token stream
        this.tokenSubject.next(msg['content'] || '');
        this.doneSubject.next({ source: 'agent' });
        break;
      case 'agent_joined':
        this.thinkingSubject.next({
          status: msg['message'] || 'An agent has joined',
          node: 'agent_join'
        });
        break;
      case 'session_resolved':
        this.doneSubject.next({ source: 'resolved' });
        break;
      case 'PONG':
        // Heartbeat acknowledged — connection is alive
        break;
      case 'error':
        console.error('[Chat WS] Backend error:', msg['message']);
        this.errorSubject.next(msg['message'] || 'An error occurred');
        break;
      default:
        console.warn('[Chat WS] Unknown message type:', msg);
    }
  }

  sendMessage(text: string): void {
    const payload = { type: 'user_message', content: text };

    if (this.socket$ && !this.socket$.closed && this.connected) {
      this.socket$.next(payload);
    } else {
      // Queue message for delivery after reconnection
      console.warn('[Chat WS] Queuing message (not connected yet)');
      this.messageQueue.push(payload);
    }
  }

  /** Send a raw message bypassing the connected guard (for handshake) */
  private sendRaw(msg: any): void {
    if (this.socket$ && !this.socket$.closed) {
      this.socket$.next(msg);
    }
  }

  /** Flush queued messages after connection is confirmed */
  private flushMessageQueue(): void {
    if (this.messageQueue.length > 0) {
      console.log(`[Chat WS] Flushing ${this.messageQueue.length} queued messages`);
      for (const msg of this.messageQueue) {
        this.sendRaw(msg);
      }
      this.messageQueue = [];
    }
  }

  /** Start periodic PING heartbeat to detect dead connections */
  private startPing(): void {
    this.stopPing();
    this.pingSubscription = timer(25000, 25000).pipe(
      takeUntil(this.destroy$)
    ).subscribe(() => {
      this.sendRaw({ type: 'PING' });
    });
  }

  /** Stop the heartbeat timer */
  private stopPing(): void {
    if (this.pingSubscription) {
      this.pingSubscription.unsubscribe();
      this.pingSubscription = null;
    }
  }

  disconnect(): void {
    this.stopPing();
    this.connected = false;
    this.messageQueue = [];
    if (this.socket$) {
      this.socket$.complete();
      this.socket$ = null;
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    this.disconnect();
  }
}
