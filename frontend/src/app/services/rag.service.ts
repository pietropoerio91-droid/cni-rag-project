import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
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
      const xhr = new XMLHttpRequest();
      let lastIndex = 0;

      xhr.open('POST', `${this.apiUrl}/query/stream`);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.responseType = 'text';

      xhr.onprogress = () => {
        const newData = xhr.responseText.slice(lastIndex);
        lastIndex = xhr.responseText.length;

        const lines = newData.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const parsed = JSON.parse(line.slice(6));
              observer.next(parsed);
            } catch {
              observer.next(line.slice(6));
            }
          }
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          observer.complete();
        } else {
          observer.error(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
        }
      };

      xhr.onerror = () => {
        observer.error(new Error('Errore di connessione al server'));
      };

      xhr.send(JSON.stringify(request));

      return () => xhr.abort();
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
