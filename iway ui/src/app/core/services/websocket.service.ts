import { Injectable } from '@angular/core';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { Observable, of } from 'rxjs';
import { catchError, retry } from 'rxjs/operators';

export interface WsMessage {
  type: string;
  payload: any;
}

@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private socket$!: WebSocketSubject<WsMessage>;
  private readonly WS_ENDPOINT = 'ws://localhost:3000/ws';

  public connect(): void {
    if (!this.socket$ || this.socket$.closed) {
      this.socket$ = webSocket(this.WS_ENDPOINT);
      
      this.socket$.pipe(
        retry({ count: 5, delay: 2000 }),
        catchError(err => {
          console.error('WebSocket Error', err);
          return of({ type: 'ERROR', payload: err });
        })
      ).subscribe();
    }
  }

  public getMessages(): Observable<WsMessage> {
    if (!this.socket$) {
      this.connect();
    }
    return this.socket$.asObservable();
  }

  public sendMessage(msg: WsMessage): void {
    if (this.socket$) {
      this.socket$.next(msg);
    }
  }
}
