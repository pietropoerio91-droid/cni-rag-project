import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, Subject, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { QueryRequest, QueryResponse, HealthResponse, IngestResponse, IngestStatus, QdrantStatsResponse, QdrantDocumentsResponse, QdrantAnalyticsResponse, QdrantCoverageResponse, BenchmarkResponse, BenchmarkFullRun, QueryStatsResponse } from '../models/rag.models';

@Injectable({ providedIn: 'root' })
export class RagService {
  private apiUrl = 'http://localhost:8000/api/v1';
  chatReset$ = new Subject<void>();

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

  getIngestStatus(): Observable<IngestStatus> {
    return this.http.get<IngestStatus>(`${this.apiUrl}/ingest/status`).pipe(
      catchError(() => throwError(() => new Error('Status non disponibile')))
    );
  }

  getQdrantStats(): Observable<QdrantStatsResponse> {
    return this.http.get<QdrantStatsResponse>(`${this.apiUrl}/qdrant/stats`).pipe(
      catchError(() => throwError(() => new Error('Qdrant non raggiungibile')))
    );
  }

  getQdrantAnalytics(): Observable<QdrantAnalyticsResponse> {
    return this.http.get<QdrantAnalyticsResponse>(`${this.apiUrl}/qdrant/analytics`).pipe(
      catchError(() => throwError(() => new Error('Analytics non disponibili')))
    );
  }

  getQdrantCoverage(): Observable<QdrantCoverageResponse> {
    return this.http.get<QdrantCoverageResponse>(`${this.apiUrl}/qdrant/coverage`).pipe(
      catchError(() => throwError(() => new Error('Copertura non disponibile')))
    );
  }

  getQdrantDocuments(offset = 0, limit = 20, search?: string): Observable<QdrantDocumentsResponse> {
    let params = `?offset=${offset}&limit=${limit}`;
    if (search) params += `&search=${encodeURIComponent(search)}`;
    return this.http.get<QdrantDocumentsResponse>(`${this.apiUrl}/qdrant/documents${params}`).pipe(
      catchError(this.handleError)
    );
  }

  getBenchmarkResults(): Observable<BenchmarkResponse> {
    return this.http.get<BenchmarkResponse>(`${this.apiUrl}/benchmark`).pipe(
      catchError(() => throwError(() => new Error('Benchmark non disponibile')))
    );
  }

  getBenchmarkRun(timestamp: string): Observable<BenchmarkFullRun> {
    return this.http.get<BenchmarkFullRun>(`${this.apiUrl}/benchmark/runs/${timestamp}`).pipe(
      catchError(() => throwError(() => new Error('Run non trovato')))
    );
  }

  getQueryStats(): Observable<QueryStatsResponse> {
    return this.http.get<QueryStatsResponse>(`${this.apiUrl}/query/stats`).pipe(
      catchError(() => throwError(() => new Error('Statistiche query non disponibili')))
    );
  }

  private handleError(error: HttpErrorResponse) {
    const message = error.error?.detail || error.message || 'Errore sconosciuto';
    return throwError(() => new Error(message));
  }
}
