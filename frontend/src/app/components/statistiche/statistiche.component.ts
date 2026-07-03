import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RagService } from '../../services/rag.service';
import { QdrantAnalyticsResponse, QdrantDocument, QdrantDocumentsResponse, QdrantCoverageResponse } from '../../models/rag.models';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-statistiche',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="stats-page">
      <div class="stats-header">
        <h1>Statistiche</h1>
        <p class="subtitle">Analisi dei documenti indicizzati nel database vettoriale</p>
      </div>

      <div class="loading" *ngIf="!analytics && !error">
        <div class="spinner"></div>
        <p>Analisi dei documenti in corso...</p>
      </div>

      <div class="error" *ngIf="error">{{ error }}</div>

      <ng-container *ngIf="analytics">
        <div class="summary-grid">
          <div class="summary-card">
            <div class="summary-value">{{ analytics.total_documents }}</div>
            <div class="summary-label">
              Documenti indicizzati
              <span class="tooltip-wrap">
                <span class="tooltip-icon">i</span>
                <span class="tooltip-text">Numero totale di documenti processati e indicizzati nel database vettoriale Qdrant</span>
              </span>
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-value">{{ formatNumber(analytics.avg_content_length) }}</div>
            <div class="summary-label">
              Lunghezza media
              <span class="tooltip-wrap">
                <span class="tooltip-icon">i</span>
                <span class="tooltip-text">Media aritmetica della lunghezza in caratteri del contenuto testuale di tutti i documenti indicizzati</span>
              </span>
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-value">{{ formatNumber(analytics.median_content_length) }}</div>
            <div class="summary-label">
              Lunghezza mediana
              <span class="tooltip-wrap">
                <span class="tooltip-icon">i</span>
                <span class="tooltip-text">Valore centrale della distribuzione delle lunghezze: meno sensibile ai valori estremi rispetto alla media</span>
              </span>
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-value">{{ totalCategories }}</div>
            <div class="summary-label">
              Categorie
              <span class="tooltip-wrap">
                <span class="tooltip-icon">i</span>
                <span class="tooltip-text">Numero di categorie tematiche assegnate ai documenti durante l'indicizzazione</span>
              </span>
            </div>
          </div>
        </div>

        <div class="charts-grid">
          <div class="chart-card">
            <h3 class="chart-title">
              Documenti per Categoria
              <span class="tooltip-wrap chart-tooltip">
                <span class="tooltip-icon">i</span>
                <span class="tooltip-text">Distribuzione dei documenti raggruppati per categoria tematica. Ogni barra rappresenta il numero di documenti appartenenti a quella categoria</span>
              </span>
            </h3>
            <div class="bar-chart">
              <div class="bar-row" *ngFor="let item of chartData.categories">
                <span class="bar-label">{{ item.label }}</span>
                <div class="bar-track">
                  <div class="bar-fill" [style.width.%]="item.pct" [style.background]="item.color"></div>
                </div>
                <span class="bar-value">{{ item.value }}</span>
              </div>
            </div>
          </div>

          <div class="chart-card">
            <h3 class="chart-title">
              Lunghezza Contenuti
              <span class="tooltip-wrap chart-tooltip">
                <span class="tooltip-icon">i</span>
                <span class="tooltip-text">Distribuzione dei documenti in base alla lunghezza in caratteri, suddivisa in intervalli. Utile per capire la dimensione tipica dei contenuti indicizzati</span>
              </span>
            </h3>
            <div class="bar-chart">
              <div class="bar-row" *ngFor="let item of chartData.lengths">
                <span class="bar-label">{{ item.label }}</span>
                <div class="bar-track">
                  <div class="bar-fill" [style.width.%]="item.pct" [style.background]="item.color"></div>
                </div>
                <span class="bar-value">{{ item.value }}</span>
              </div>
            </div>
          </div>

          <div class="chart-card">
            <h3 class="chart-title">
              Top Fonti
              <span class="tooltip-wrap chart-tooltip">
                <span class="tooltip-icon">i</span>
                <span class="tooltip-text">Le 10 fonti (URL) che hanno contribuito con il maggior numero di chunk (segmenti) al database. Un documento lungo viene suddiviso in più chunk, quindi uno stesso PDF può comparire più volte</span>
              </span>
            </h3>
            <div class="bar-chart sources-chart">
              <div class="bar-row source-row" *ngFor="let item of chartData.sources">
                <div class="bar-track source-bar" [title]="item.fullUrl || item.label">
                  <div class="bar-fill" [style.width.%]="item.pct" [style.background]="item.color"></div>
                </div>
                <span class="bar-value">{{ item.value }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="coverage-card" *ngIf="coverage">
          <h3 class="chart-title">
            Copertura Dati per Sezione
            <span class="tooltip-wrap chart-tooltip">
              <span class="tooltip-icon">i</span>
              <span class="tooltip-text">Sections with poor coverage have few chunks or very short content — queries about these topics may fall back. Red = insufficient data, green = queryable.</span>
            </span>
          </h3>
          <div class="coverage-list">
            <div class="coverage-row" *ngFor="let s of coverage.sections">
              <span class="coverage-label">{{ s.category }}</span>
              <div class="coverage-bar-track">
                <div class="coverage-bar-fill" [style.width.%]="coverageBarPct(s)" [style.background]="s.poor_coverage ? '#dc2626' : '#16a34a'"></div>
              </div>
              <span class="coverage-value">{{ s.chunks }} chunk · {{ s.avg_content_length }} car.</span>
              <span class="coverage-badge" [class.bad]="s.poor_coverage" [class.good]="!s.poor_coverage">{{ s.poor_coverage ? 'POCO DATI' : 'OK' }}</span>
            </div>
          </div>
        </div>
      </ng-container>
    </div>
  `,
  styles: [`
    .stats-page {
      max-width: 1100px;
      margin: 0 auto;
      padding: 32px 24px 80px;
    }
    .stats-header {
      margin-bottom: 28px;
    }
    .stats-header h1 {
      font-size: 24px;
      font-weight: 700;
      color: var(--text);
    }
    .subtitle {
      color: var(--text-secondary);
      margin-top: 4px;
    }
    .loading {
      text-align: center;
      padding: 60px 0;
      color: var(--text-secondary);
    }
    .spinner {
      width: 32px;
      height: 32px;
      border: 3px solid var(--border);
      border-top-color: var(--primary);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin: 0 auto 12px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .error {
      text-align: center;
      padding: 20px;
      color: var(--error);
      background: #fef2f2;
      border-radius: 8px;
    }

    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-bottom: 32px;
    }
    .summary-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      text-align: center;
      box-shadow: var(--shadow);
    }
    .summary-value {
      font-size: 28px;
      font-weight: 700;
      color: var(--primary);
    }
    .summary-label {
      font-size: 13px;
      color: var(--text-secondary);
      margin-top: 4px;
    }

    .charts-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 20px;
    }
    .chart-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      box-shadow: var(--shadow);
    }
    .chart-title {
      font-size: 15px;
      font-weight: 600;
      color: var(--text);
      margin-bottom: 16px;
    }
    .bar-chart {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .bar-row {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .bar-label {
      width: 100px;
      font-size: 12px;
      color: var(--text-secondary);
      flex-shrink: 0;
      text-align: right;
    }
    .bar-label.truncate {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .bar-track {
      flex: 1;
      height: 20px;
      background: var(--bg);
      border-radius: 6px;
      overflow: hidden;
    }
    .source-row .bar-label {
      display: none;
    }
    .source-row {
      gap: 0 !important;
    }
    .source-bar {
      cursor: pointer;
    }
    .bar-track:hover .bar-fill {
      filter: brightness(1.2);
    }
    .sources-chart {
      gap: 4px !important;
    }
    .source-row .bar-value {
      width: 36px;
      padding-left: 8px;
    }
    .bar-fill {
      height: 100%;
      border-radius: 6px;
      transition: width 0.6s ease;
      min-width: 2px;
    }
    .bar-value {
      width: 40px;
      font-size: 12px;
      font-weight: 600;
      color: var(--text);
      text-align: right;
      flex-shrink: 0;
    }

    .tooltip-wrap {
      position: relative;
      display: inline-flex;
      align-items: center;
      margin-left: 4px;
      cursor: help;
      vertical-align: middle;
    }
    .tooltip-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: var(--border);
      color: var(--text-secondary);
      font-size: 10px;
      font-weight: 700;
      font-style: italic;
      font-family: serif;
      transition: background 0.15s, color 0.15s;
    }
    .tooltip-wrap:hover .tooltip-icon {
      background: var(--primary);
      color: #fff;
    }
    .tooltip-text {
      visibility: hidden;
      opacity: 0;
      position: absolute;
      bottom: calc(100% + 8px);
      left: 50%;
      transform: translateX(-50%);
      background: #1e293b;
      color: #e2e8f0;
      font-size: 12px;
      font-weight: 400;
      font-style: normal;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      padding: 8px 12px;
      border-radius: 8px;
      white-space: normal;
      width: 260px;
      text-align: center;
      line-height: 1.4;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      z-index: 100;
      pointer-events: none;
      transition: opacity 0.15s, visibility 0.15s;
    }
    .tooltip-text::after {
      content: '';
      position: absolute;
      top: 100%;
      left: 50%;
      transform: translateX(-50%);
      border: 6px solid transparent;
      border-top-color: #1e293b;
    }
    .tooltip-wrap:hover .tooltip-text {
      visibility: visible;
      opacity: 1;
    }
    .chart-tooltip .tooltip-text {
      width: 300px;
    }

    .coverage-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      margin-top: 20px;
      box-shadow: var(--shadow);
    }
    .coverage-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .coverage-row {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .coverage-label {
      width: 100px;
      font-size: 12px;
      color: var(--text-secondary);
      flex-shrink: 0;
      text-align: right;
    }
    .coverage-bar-track {
      flex: 1;
      height: 16px;
      background: var(--bg);
      border-radius: 6px;
      overflow: hidden;
    }
    .coverage-bar-fill {
      height: 100%;
      border-radius: 6px;
      transition: width 0.6s ease;
      min-width: 4px;
    }
    .coverage-value {
      font-size: 11px;
      color: var(--text-secondary);
      width: 140px;
      flex-shrink: 0;
    }
    .coverage-badge {
      font-size: 10px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
      text-transform: uppercase;
    }
    .coverage-badge.good {
      background: #dcfce7;
      color: #16a34a;
    }
    .coverage-badge.bad {
      background: #fef2f2;
      color: #dc2626;
    }
  `]
})
export class StatisticheComponent implements OnInit, OnDestroy {
  analytics: QdrantAnalyticsResponse | null = null;
  coverage: QdrantCoverageResponse | null = null;
  error = '';
  private sub = new Subscription();

  CHART_COLORS = [
    '#1a56db', '#16a34a', '#f59e0b', '#dc2626', '#8b5cf6',
    '#ec4899', '#06b6d4', '#f97316', '#14b8a6', '#6366f1',
  ];

  constructor(private ragService: RagService) {}

  ngOnInit() {
    this.sub.add(
      this.ragService.getQdrantAnalytics().subscribe({
        next: (a) => { this.analytics = a; },
        error: () => { this.error = 'Impossibile caricare le statistiche. Verifica che API e Qdrant siano in esecuzione.'; },
      })
    );
    this.sub.add(
      this.ragService.getQdrantCoverage().subscribe({
        next: (c) => { this.coverage = c; },
        error: () => {},
      })
    );
  }

  ngOnDestroy() {
    this.sub.unsubscribe();
  }

  get totalCategories(): number {
    return this.analytics ? Object.keys(this.analytics.categories).length : 0;
  }

  coverageBarPct(s: { chunks: number; avg_content_length: number }): number {
    const maxChunks = Math.max(...(this.coverage?.sections.map(x => x.chunks) || [1]), 1);
    return (s.chunks / maxChunks) * 100;
  }

  formatNumber(n: number): string {
    return n.toLocaleString('it-IT', { maximumFractionDigits: 0 });
  }

  shortenUrl(url: string): string {
    try {
      const u = new URL(url);
      const parts = u.pathname.replace(/\/$/, '').split('/');
      return parts[parts.length - 1] || u.pathname;
    } catch {
      return url.length > 50 ? url.slice(0, 47) + '…' : url;
    }
  }

  get chartData() {
    if (!this.analytics) return { categories: [], lengths: [], sources: [] };

    const catEntries = Object.entries(this.analytics.categories);
    const catMax = Math.max(...catEntries.map(([, v]) => v), 1);
    const categories = catEntries.map(([k, v], i) => ({
      label: k, value: v, pct: (v / catMax) * 100,
      color: this.CHART_COLORS[i % this.CHART_COLORS.length],
    }));

    const lenEntries = Object.entries(this.analytics.content_length_buckets);
    const lenMax = Math.max(...lenEntries.map(([, v]) => v), 1);
    const lengths = lenEntries.map(([k, v], i) => ({
      label: k, value: v, pct: (v / lenMax) * 100,
      color: this.CHART_COLORS[(i + 3) % this.CHART_COLORS.length],
    }));

    const srcMax = Math.max(...this.analytics.top_sources.map(s => s.count), 1);
    const sources = this.analytics.top_sources.map((s, i) => ({
      label: this.shortenUrl(s.name), value: s.count, pct: (s.count / srcMax) * 100,
      color: this.CHART_COLORS[(i + 6) % this.CHART_COLORS.length],
      fullUrl: s.name,
    }));

    return { categories, lengths, sources };
  }
}
