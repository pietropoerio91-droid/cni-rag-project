import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RagService } from '../../services/rag.service';
import { QdrantAnalyticsResponse, QdrantDocument, QdrantDocumentsResponse } from '../../models/rag.models';
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
            <div class="summary-label">Documenti indicizzati</div>
          </div>
          <div class="summary-card">
            <div class="summary-value">{{ formatNumber(analytics.avg_content_length) }}</div>
            <div class="summary-label">Lunghezza media (caratteri)</div>
          </div>
          <div class="summary-card">
            <div class="summary-value">{{ formatNumber(analytics.median_content_length) }}</div>
            <div class="summary-label">Lunghezza mediana (caratteri)</div>
          </div>
          <div class="summary-card">
            <div class="summary-value">{{ totalCategories }}</div>
            <div class="summary-label">Categorie</div>
          </div>
        </div>

        <div class="charts-grid">
          <div class="chart-card">
            <h3 class="chart-title">Documenti per Categoria</h3>
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
            <h3 class="chart-title">Lunghezza Contenuti</h3>
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
            <h3 class="chart-title">Top Fonti</h3>
            <div class="bar-chart">
              <div class="bar-row" *ngFor="let item of chartData.sources">
                <span class="bar-label truncate" [title]="item.label">{{ item.label }}</span>
                <div class="bar-track">
                  <div class="bar-fill" [style.width.%]="item.pct" [style.background]="item.color"></div>
                </div>
                <span class="bar-value">{{ item.value }}</span>
              </div>
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
  `]
})
export class StatisticheComponent implements OnInit, OnDestroy {
  analytics: QdrantAnalyticsResponse | null = null;
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
  }

  ngOnDestroy() {
    this.sub.unsubscribe();
  }

  get totalCategories(): number {
    return this.analytics ? Object.keys(this.analytics.categories).length : 0;
  }

  formatNumber(n: number): string {
    return n.toLocaleString('it-IT', { maximumFractionDigits: 0 });
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
      label: s.name, value: s.count, pct: (s.count / srcMax) * 100,
      color: this.CHART_COLORS[(i + 6) % this.CHART_COLORS.length],
    }));

    return { categories, lengths, sources };
  }
}
