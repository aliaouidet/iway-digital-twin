# AI Support Monitoring System - Architecture & Implementation Plan

> [!NOTE]
> This document details the production-grade architecture for integrating the RAG-based AI support monitoring backend. Since the current workspace (`/home/azmi/Desktop/iway ui`) is empty, please review this plan and let me know if you would like me to bootstrap a new Angular application using this architecture, or if you plan to import an existing codebase for the integration.

## 1. Architecture Overview

We will employ a highly scalable, feature-based modular architecture tailored for performance, clear dependency management, and high observability into the AI workflows. 

**Key Technologies:**
- **Framework:** Angular 18+ (Standalone Components & Signals can be mixed with traditional modules where optimal)
- **State Management:** NgRx (Store, Effects, Entity, Selectors)
- **Real-Time Data:** RxJS and WebSockets (or RxStomp for STOMP over WebSockets)
- **UI/UX Stack:** TailwindCSS for utility styling + Angular Material (or PrimeNG/Taiga UI) for complex data grids and accessible UI primitives. Apache ECharts for performant, reactive charting in the Dashboard.

---

## 2. Feature Modules Breakdown

### Dashboard Module
- **Metrics Displays:** Overview cards for total requests, resolved by RAG, AI escalation count, human escalation count.
- **Charts:** 
  - *Response Time:* Line chart tracking RAG vs AI latency.
  - *Failure/Fallback Rate:* Doughnut chart showing % of queries escalated.
- **Real-time:** Driven by Server-Sent Events (SSE) or WebSockets to live-update metrics without page unloads.

### Ticket Management Module
- **Ticket List Grid:** Paginator, sortable columns (Status, Confidence Score, Date, Assigned To). 
- **Ticket Detail View:** Side-by-side or tabbed view showing:
  - User original query.
  - Expandable RAG context (document chunks retrieved, source links).
  - The AI generated response and confidence score.
- **Actions:** Buttons to `Reprocess Ticket` (triggering a fresh backend call), `Assign to Human`, or `Edit AI Response` before officially resolving.

### Chat / Message System Module
- **Chat Interface:** Simulates the user's conversational flow.
- **Status Tags:** Each message component visually indicates its processor (`[RAG]`, `[AI Model]`, `[Failed - Human Pending]`) via distinct color-coded badges.
- **Live Updates:** WebSocket subscription updating the specific ticket's conversation history in real-time.

### Logs & Monitoring Module
- **Log Data Grid:** Deep dive into system internals.
  - Columns: Query, similarity scores of retrieved chunks, LLM prompt used, generation time, outcome.
- **Filters & Export:** Advanced filtering by date boundaries, error typologies, and users. Includes a utility service for exporting the current grid state to CSV/JSON.

### AI Insights Module
- **Analytics View:** Aggregations showing frequent fallback queries, identifying gaps in knowledge base.
- **Actionable Suggestions:** A dashboard suggesting missing documentation topics based on clusters of failed queries.

### Admin Panel Module
- **System Configuration Form:** Reactive forms to set RAG confidence thresholds, adjust system prompts, tune retry policies, and configure vector DB data sources.

---

## 3. State Management (NgRx)

To ensure predictable data flow across complex features (like real-time metric updates while viewing a ticket):
- **Store Structure:**
  - `metrics`: Global metric numbers, refreshed incrementally via socket actions.
  - `tickets`: Managed via `@ngrx/entity` to easily handle large lists, selections, and individual ticket updates.
  - `activeTicket`: The currently viewed conversation + associated document chunks.
  - `logs`: Pagination/filter state and cached log records.
- **Effects:** Handle all REST/WebSocket API mapping, isolating side-effects from UI components.

---

## 4. Backend Integration Pattern

The frontend will communicate via dedicated Angular Services abstracting standard `HttpClient` and a WebSocket wrapper service:

- **REST API (`HttpClient`):**
  - GET `/api/v1/tickets`, `/api/v1/tickets/:id` (Init requests)
  - GET `/api/v1/logs`, `/api/v1/metrics`
  - POST `/api/v1/query` (Manual reprocessing / interaction)
- **WebSockets (`rxjs/webSocket`):**
  - `ws://backend/ws/metrics` (Live ticker updates)
  - `ws://backend/ws/tickets/:id` (Live chat event streams)

---

## 5. UI/UX Suggestions

- **Theme:** Clean, modern "Dark Mode" capable SAAS look. Deep slate backgrounds with vibrant accents (e.g., Green for RAG resolved, Amber for AI Fallback, Rose for Human Required).
- **Libraries:**
  - `ngx-echarts` for dynamic, beautiful data charts.
  - `PrimeNG` or `Angular Material` for advanced DataTables (virtual scrolling for logs).
  - `TailwindCSS` for extremely fast, responsive structural styling without CSS bloat.

---

## 6. Deliverables: Folder Structure

If using modern Angular (v15+), a domain-driven folder approach fits beautifully:

```text
src/app/
├── core/                       # Singleton services, interceptors, guards
│   ├── interceptors/           # HTTP error handling, auth tokens
│   ├── services/
│   │   ├── api.service.ts
│   │   ├── websocket.service.ts
│   │   └── notification.service.ts
│   └── state/                  # Root NgRx state
│       ├── app.state.ts
│       └── root.reducer.ts
├── shared/                     # Reusable dumb components, pipes, directives
│   ├── components/
│   │   ├── status-badge/
│   │   ├── data-card/
│   │   └── chat-bubble/
│   └── models/                 # Global TS Interfaces
│       ├── ticket.interface.ts
│       └── metrics.interface.ts
├── features/                   # Lazy-loaded feature domains
│   ├── dashboard/
│   │   ├── state/              # Feature-specific NgRx
│   │   ├── dashboard.component.ts
│   │   └── dashboard.component.html
│   ├── tickets/
│   │   ├── components/
│   │   │   ├── ticket-list/
│   │   │   └── ticket-detail/
│   │   ├── services/
│   │   │   └── ticket-api.service.ts
│   │   └── state/
│   ├── chat/
│   ├── logs/
│   ├── insights/
│   └── admin/
├── app.routes.ts               # Sub-routing definitions
└── app.config.ts               # App-wide providers (HttpClient, NgRx Store)
```

---

## 7. Example Code Snippets

### A. WebSocket Real-Time Integration (`websocket.service.ts`)
A robust WebSocket service that handles reconnections and multiplexing.

```typescript
import { Injectable } from '@angular/core';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { Observable, timer, Subject, EMPTY } from 'rxjs';
import { retryWhen, tap, delayWhen, switchMap, catchError } from 'rxjs/operators';
import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class WebSocketService {
  private socket$!: WebSocketSubject<any>;
  private messagesSubject$ = new Subject<any>();

  public messages$: Observable<any> = this.messagesSubject$.asObservable();

  public connect(cfg: { endpoint: string }): void {
    if (!this.socket$ || this.socket$.closed) {
      this.socket$ = this.getNewWebSocket(`${environment.wsUrl}/${cfg.endpoint}`);
      
      this.socket$.pipe(
        retryWhen(errors =>
          errors.pipe(
            tap(err => console.error('WebSocket Error', err)),
            delayWhen(() => timer(5000)) // Reconnect after 5 seconds
          )
        ),
        catchError(err => {
          console.error(err);
          return EMPTY;
        })
      ).subscribe({
        next: (msg) => this.messagesSubject$.next(msg),
        error: (err) => console.error(err),
        complete: () => console.warn('WebSocket connection closed')
      });
    }
  }

  private getNewWebSocket(url: string) {
    return webSocket({
      url,
      openObserver: {
        next: () => console.log('[DataService]: connection ok')
      },
      closeObserver: {
        next: () => console.log('[DataService]: connection closed')
      }
    });
  }

  public sendMessage(msg: any) {
    if (this.socket$) {
      this.socket$.next(msg);
    }
  }
}
```

### B. Dashboard Component with NgRx integration (`dashboard.component.ts`)

```typescript
import { Component, OnInit, OnDestroy } from '@angular/core';
import { Store } from '@ngrx/store';
import { Observable, Subscription } from 'rxjs';
import { MetricsState } from '../state/metrics.reducer';
import { loadMetrics, updateRealtimeMetrics } from '../state/metrics.actions';
import { selectTotalRequests, selectEscalationRate } from '../state/metrics.selectors';
import { WebSocketService } from 'src/app/core/services/websocket.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss']
})
export class DashboardComponent implements OnInit, OnDestroy {
  totalRequests$!: Observable<number>;
  escalationRate$!: Observable<number>;
  private wsSubscription!: Subscription;

  constructor(
    private store: Store<{ metrics: MetricsState }>,
    private wsService: WebSocketService
  ) {
    this.totalRequests$ = this.store.select(selectTotalRequests);
    this.escalationRate$ = this.store.select(selectEscalationRate);
  }

  ngOnInit() {
    // 1. Dispatch action to load initial metrics via REST
    this.store.dispatch(loadMetrics());

    // 2. Connect to metrics websocket
    this.wsService.connect({ endpoint: 'metrics' });

    // 3. Listen to live updates and update NgRx Store
    this.wsSubscription = this.wsService.messages$.subscribe((liveData) => {
      this.store.dispatch(updateRealtimeMetrics({ payload: liveData }));
    });
  }

  ngOnDestroy() {
    if (this.wsSubscription) {
      this.wsSubscription.unsubscribe();
    }
  }
}
```

### C. Ticket Interface (`ticket.interface.ts`)
Ensuring type safety for complex, multi-state data objects.

```typescript
export type ProcessingStatus = 'RAG_RESOLVED' | 'AI_HANDLED' | 'HUMAN_REQUIRED';

export interface RagContext {
  documentId: string;
  chunkText: string;
  similarityScore: number;
  sourceUrl?: string;
}

export interface SupportTicket {
  id: string;
  userId: string;
  query: string;
  status: ProcessingStatus;
  ragContext: RagContext[];
  aiResponse?: string;
  confidenceScore: number;
  createdAt: string;
  assignedToHuman?: boolean;
}
```

### D. Centralized Ticket Service (`ticket-api.service.ts`)

```typescript
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { SupportTicket } from 'src/app/shared/models/ticket.interface';
import { environment } from 'src/environments/environment';

@Injectable({
  providedIn: 'root'
})
export class TicketApiService {
  private readonly baseUrl = `${environment.apiUrl}/tickets`;

  constructor(private http: HttpClient) {}

  getAllTickets(): Observable<SupportTicket[]> {
    return this.http.get<SupportTicket[]>(this.baseUrl);
  }

  getTicketById(id: string): Observable<SupportTicket> {
    return this.http.get<SupportTicket>(`${this.baseUrl}/${id}`);
  }

  reprocessTicket(id: string, overridePrompt?: string): Observable<SupportTicket> {
    return this.http.post<SupportTicket>(`${this.baseUrl}/${id}/reprocess`, {
      prompt: overridePrompt
    });
  }

  assignToHuman(id: string, agentId: string): Observable<void> {
    return this.http.patch<void>(`${this.baseUrl}/${id}/assign`, { agentId });
  }
}
```

---

## 8. Best Practices & Performance Considerations

1. **ChangeDetectionStrategy.OnPush**: Use `OnPush` across all feature components (`Dashboard`, `TicketList`, `ChatInterface`), leveraging the `async` pipe with NgRx selectors to trigger UI updates only when new state references are emitted. This radically improves rendering speed, especially for live websocket data.
2. **Virtual Scrolling**: The Logs View and Chat History should utilize `@angular/cdk/scrolling` for virtual scrolling to prevent DOM bloating when thousands of logs or chat messages are loaded.
3. **Lazy Loading**: Route-level code splitting (`loadChildren` or `loadComponent` in Angular 14+) must be used for each feature module (Admin, Logs, Dashboard). The Admin panel in particular might contain heavy dependencies (like Monaco Editor for prompt tuning) that shouldn't load for default users.
4. **Resilient Websockets**: Implement exponential backoff for WebSocket reconnections (as shown in the example) to avoid hammering the backend during brief outages. Use `SharedWorker` if you ever plan to run multiple tabs to multiplex the WebSocket connection, conserving backend resources.

---

## Next Steps / Open Questions

> [!WARNING] 
> **User Feedback Needed:**
> 1. Should I initialize a brand-new Angular project in `/home/azmi/Desktop/iway ui` and set up this structure automatically?
> 2. Are there any specific UI libraries (e.g., Angular Material vs. Tailwind UI vs. PrimeNG) you strongly prefer?
> 3. Does the NgRx state management fit your team's current patterns, or would you prefer a more lightweight approach like Angular 16+ Signals?
