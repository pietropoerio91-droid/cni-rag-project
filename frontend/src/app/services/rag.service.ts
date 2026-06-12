import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { QueryRequest, QueryResponse, HealthResponse, IngestResponse } from '../models/rag.models';

@Injectable({ providedIn: 'root' })
export class RagService {
  private apiUrl = 'http://localhost:8000/api/v1';

  constructor(private http: HttpClient) {}

  query(request: QueryRequest): Observable<QueryResponse> {
    return this.http.post<QueryResponse>(`${this.apiUrl}/query`, request).pipe(
      catchError(this.handleError)
    );
  }

  queryStream(request: QueryRequest): Observable<string> {
    return new Observable<string>((observer) => {
      const eventSource = new EventSourcePolyfill(`${this.apiUrl}/query/stream`, {
        method: 'POST',
        body: JSON.stringify(request),
        headers: { 'Content-Type': 'application/json' },
      });

      eventSource.onmessage = (event) => {
        observer.next(event.data);
      };

      eventSource.onerror = (error) => {
        observer.error(error);
        eventSource.close();
      };

      return () => eventSource.close();
    });
  }

  health(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${this.apiUrl}/health`).pipe(
      catchError(() => throwError(() => new Error('API non raggiungibile')))
    );
  }

  ingest(): Observable<IngestResponse> {
    return this.http.post<IngestResponse>(`${this.apiUrl}/ingest`, {}).pipe(
      catchError(this.handleError)
    );
  }

  private handleError(error: HttpErrorResponse) {
    const message = error.error?.detail || error.message || 'Errore sconosciuto';
    return throwError(() => new Error(message));
  }
}

class EventSourcePolyfill {
  private xhr: XMLHttpRequest;
  private lastIndex = 0;

  constructor(url: string, options: { method: string; body: string; headers: Record<string, string> }) {
    this.xhr = new XMLHttpRequest();
    this.xhr.open(options.method, url);
    for (const [key, value] of Object.entries(options.headers)) {
      this.xhr.setRequestHeader(key, value);
    }
    this.xhr.responseType = 'text';
    this.xhr.send(options.body);
  }

  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((error: any) => void) | null = null;

  close() {
    this.xhr.abort();
  }
}
