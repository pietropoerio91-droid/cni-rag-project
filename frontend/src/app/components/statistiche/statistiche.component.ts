import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RagService } from '../../services/rag.service';
import { QdrantAnalyticsResponse, QdrantDocument, QdrantDocumentsResponse, QdrantCoverageResponse, BenchmarkResponse, BenchmarkResultItem, BenchmarkFullRun, QueryStatsResponse, QueryMetricsResponse } from '../../models/rag.models';
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

      <div class="tabs">
        <button class="tab-btn" [class.active]="activeTab === 'quantitative'" (click)="activeTab='quantitative'">
          Quantitative
        </button>
        <button class="tab-btn" [class.active]="activeTab === 'qualitative'" (click)="activeTab='qualitative'; refreshQueryStats()">
          Qualitative
        </button>
      </div>

      <div class="loading" *ngIf="!analytics && !error">
        <div class="spinner"></div>
        <p>Analisi dei documenti in corso...</p>
      </div>

      <div class="error" *ngIf="error">{{ error }}</div>

      <ng-container *ngIf="analytics">
        <div *ngIf="activeTab === 'quantitative'">
        <div class="summary-grid">
          <div class="summary-card">
            <div class="summary-value">{{ analytics.total_chunks }}</div>
            <div class="summary-label">
              Chunk indicizzati
              <span class="tooltip-wrap">
                <span class="tooltip-icon">i</span>
                <span class="tooltip-text">Segmenti indicizzati nel database vettoriale. Ogni documento sorgente è suddiviso in più chunk da 1.500 caratteri</span>
              </span>
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-value">{{ analytics.total_documents }}</div>
            <div class="summary-label">
              Documenti sorgente
              <span class="tooltip-wrap">
                <span class="tooltip-icon">i</span>
                <span class="tooltip-text">Numero di documenti originali crawllati e processati</span>
              </span>
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-value">{{ formatNumber(analytics.avg_content_length) }}</div>
            <div class="summary-label">
              Lunghezza media
              <span class="tooltip-wrap">
                <span class="tooltip-icon">i</span>
                <span class="tooltip-text">Lunghezza media in caratteri dei chunk indicizzati</span>
              </span>
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-value">{{ formatNumber(analytics.median_content_length) }}</div>
            <div class="summary-label">
              Lunghezza mediana
              <span class="tooltip-wrap">
                <span class="tooltip-icon">i</span>
                <span class="tooltip-text">Valore centrale della distribuzione delle lunghezze, meno sensibile ai valori estremi</span>
              </span>
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-value">{{ totalCategories }}</div>
            <div class="summary-label">
              Categorie
              <span class="tooltip-wrap">
                <span class="tooltip-icon">i</span>
                <span class="tooltip-text">Categorie tematiche assegnate ai chunk durante l'indicizzazione</span>
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
                <span class="tooltip-text">Distribuzione dei chunk per categoria tematica</span>
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
                <span class="tooltip-text">Distribuzione dei chunk per intervallo di lunghezza in caratteri</span>
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
                <span class="tooltip-text">Top 10 fonti per numero di chunk generati. Un documento lungo viene suddiviso in più chunk</span>
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
                <span class="tooltip-text">Sezioni con pochi chunk rischiano risposte poco accurate. Rosso = pochi dati, Verde = ok</span>
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
        </div>

        <div *ngIf="activeTab === 'qualitative'">

          <!-- Real-time queries section -->
          <div class="qual-section">
            <div class="section-header">
              <h2>Query in Tempo Reale
                <button class="refresh-btn" (click)="refreshQueryStats()" title="Aggiorna">⟳</button>
                <button class="export-btn" (click)="exportCsv()" title="Scarica CSV">Esporta CSV</button>
              </h2>
            </div>

            <div class="loading" *ngIf="queryStatsLoading">
              <div class="spinner"></div>
            </div>

            <ng-container *ngIf="queryStats">
              <div class="summary-grid">
                <div class="summary-card">
                  <div class="summary-value">{{ queryStats.total_queries }}</div>
                  <div class="summary-label">Query effettuate</div>
                </div>
                <div class="summary-card">
                  <div class="summary-value">{{ queryStats.avg_docs_retrieved }}</div>
                  <div class="summary-label">Media documenti recuperati</div>
                </div>
                <div class="summary-card">
                  <div class="summary-value">{{ queryStats.avg_top_score }}</div>
                  <div class="summary-label">Score medio</div>
                </div>
                <div class="summary-card">
                  <div class="summary-value">{{ (queryStats.avg_latency_ms / 1000) | number:'1.0-2' }} s</div>
                  <div class="summary-label">Latenza media</div>
                </div>
              </div>

              <div class="metrics-grid" *ngIf="queryMetrics">
                <div class="metric-card">
                  <div class="metric-value">{{ queryMetrics.mrr | number:'1.4' }}</div>
                  <div class="metric-label">
                    MRR
                    <span class="tooltip-wrap">
                      <span class="tooltip-icon">i</span>
                      <span class="tooltip-text">Mean Reciprocal Rank — quanto il sistema piazza il documento giusto al primo posto. Ideale &gt; 0.80</span>
                    </span>
                  </div>
                </div>
                <div class="metric-card">
                  <div class="metric-value">{{ queryMetrics.recall_at_1 | number:'1.4' }}</div>
                  <div class="metric-label">
                    Recall&#64;1
                    <span class="tooltip-wrap">
                      <span class="tooltip-icon">i</span>
                      <span class="tooltip-text">Frazione di query con documento rilevante al primo posto. Ideale &gt; 0.70</span>
                    </span>
                  </div>
                </div>
                <div class="metric-card">
                  <div class="metric-value">{{ queryMetrics.recall_at_3 | number:'1.4' }}</div>
                  <div class="metric-label">
                    Recall&#64;3
                    <span class="tooltip-wrap">
                      <span class="tooltip-icon">i</span>
                      <span class="tooltip-text">Frazione di documenti rilevanti nei primi 3 risultati. Ideale &gt; 0.90</span>
                    </span>
                  </div>
                </div>
                <div class="metric-card">
                  <div class="metric-value">{{ queryMetrics.recall_at_5 | number:'1.4' }}</div>
                  <div class="metric-label">
                    Recall&#64;5
                    <span class="tooltip-wrap">
                      <span class="tooltip-icon">i</span>
                      <span class="tooltip-text">Frazione di documenti rilevanti nei primi 5 risultati. Ideale &gt; 0.95</span>
                    </span>
                  </div>
                </div>
                <div class="metric-card">
                  <div class="metric-value">{{ queryMetrics.precision_at_1 | number:'1.4' }}</div>
                  <div class="metric-label">
                    Precision&#64;1
                    <span class="tooltip-wrap">
                      <span class="tooltip-icon">i</span>
                      <span class="tooltip-text">Quanto il primo risultato è pertinente. Ideale &gt; 0.70</span>
                    </span>
                  </div>
                </div>
                <div class="metric-card">
                  <div class="metric-value">{{ queryMetrics.precision_at_3 | number:'1.4' }}</div>
                  <div class="metric-label">
                    Precision&#64;3
                    <span class="tooltip-wrap">
                      <span class="tooltip-icon">i</span>
                      <span class="tooltip-text">Proporzione di risultati pertinenti nei primi 3. Ideale &gt; 0.60</span>
                    </span>
                  </div>
                </div>
                <div class="metric-card">
                  <div class="metric-value">{{ queryMetrics.classification_accuracy ?? 'N/A' }}</div>
                  <div class="metric-label">
                    Cls Acc
                    <span class="tooltip-wrap">
                      <span class="tooltip-icon">i</span>
                      <span class="tooltip-text">Accuratezza classificazione categoria. Ideale &gt; 0.90. N/A senza ground truth</span>
                    </span>
                  </div>
                </div>
              </div>

              <div class="charts-grid" *ngIf="queryStats.total_queries > 0">
                <div class="chart-card" *ngIf="queryCategoryData.length">
                  <h3 class="chart-title">Categorie</h3>
                  <div class="bar-chart">
                    <div class="bar-row" *ngFor="let item of queryCategoryData">
                      <span class="bar-label">{{ item.label }}</span>
                      <div class="bar-track">
                        <div class="bar-fill" [style.width.%]="item.pct" [style.background]="item.color"></div>
                      </div>
                      <span class="bar-value">{{ item.value }}</span>
                    </div>
                  </div>
                </div>

                <div class="chart-card" *ngIf="queryStats.recent.length > 0">
                  <h3 class="chart-title">Ultime Query</h3>
                  <div class="recent-queries">
                    <div class="recent-row" *ngFor="let q of queryStats.recent">
                      <span class="recent-q">{{ q.question }}</span>
                      <span class="recent-cat">{{ q.category }}</span>
                      <span class="recent-score">{{ q.top_score }}</span>
                      <span class="recent-docs">{{ q.doc_count }} docs</span>
                      <span class="recent-latency">{{ (q.latency_ms / 1000) | number:'1.0-2' }} s</span>
                    </div>
                  </div>
                </div>
              </div>
            </ng-container>

            <div class="benchmark-empty" *ngIf="!queryStatsLoading && !queryStats">
              <p>Nessuna query ancora registrata.</p>
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
    .tabs {
      display: flex;
      gap: 4px;
      margin-bottom: 24px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0;
    }
    .tab-btn {
      padding: 8px 20px;
      border: none;
      background: none;
      color: var(--text-secondary);
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      transition: color 0.15s, border-color 0.15s;
    }
    .tab-btn:hover {
      color: var(--text);
    }
    .tab-btn.active {
      color: var(--primary);
      border-bottom-color: var(--primary);
      font-weight: 600;
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

    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 32px;
    }
    .metric-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px 12px;
      text-align: center;
      box-shadow: var(--shadow);
    }
    .metric-value {
      font-size: 20px;
      font-weight: 700;
      color: var(--primary);
    }
    .metric-card .metric-label {
      font-size: 11px;
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
    .recent-queries {
      display: flex;
      flex-direction: column;
      gap: 4px;
      max-height: 320px;
      overflow-y: auto;
    }
    .recent-row {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 8px;
      background: var(--bg);
      border-radius: 6px;
      font-size: 11px;
    }
    .recent-q {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--text);
      font-weight: 500;
    }
    .recent-cat {
      background: var(--border);
      padding: 1px 6px;
      border-radius: 4px;
      color: var(--text-secondary);
      font-size: 10px;
      flex-shrink: 0;
    }
    .recent-score {
      width: 40px;
      text-align: right;
      color: var(--primary);
      font-weight: 600;
      flex-shrink: 0;
    }
    .recent-docs {
      width: 50px;
      text-align: right;
      color: var(--text-secondary);
      flex-shrink: 0;
    }
    .recent-latency {
      width: 50px;
      text-align: right;
      color: var(--text-secondary);
      flex-shrink: 0;
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
    .table-tip {
      margin-left: 2px;
      vertical-align: middle;
    }
    .table-tip .tooltip-text {
      width: 240px;
      font-size: 11px;
      bottom: auto;
      top: calc(100% + 6px);
    }
    .table-tip .tooltip-text::after {
      top: auto;
      bottom: 100%;
      border-top-color: transparent;
      border-bottom-color: #1e293b;
    }
    .benchmark-metrics .tooltip-wrap {
      margin-left: 1px;
    }
    .benchmark-metrics .tooltip-text {
      width: 200px;
      font-size: 11px;
      bottom: calc(100% + 6px);
    }
    .metric-label {
      display: inline-flex;
      align-items: center;
      gap: 2px;
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

    .benchmark-section {
      margin-top: 40px;
    }
    .qual-section {
      margin-bottom: 36px;
    }
    .qual-section .section-header {
      margin-bottom: 16px;
    }
    .qual-section .section-header h2 {
      font-size: 18px;
      font-weight: 700;
      color: var(--text);
    }
    .refresh-btn {
      background: none;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 2px 8px;
      font-size: 14px;
      cursor: pointer;
      color: var(--text-secondary);
      margin-left: 8px;
      vertical-align: middle;
      line-height: 1.4;
    }
    .refresh-btn:hover {
      color: var(--primary);
      border-color: var(--primary);
    }
    .export-btn {
      background: none;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 2px 10px;
      font-size: 12px;
      cursor: pointer;
      color: var(--text-secondary);
      margin-left: 6px;
      vertical-align: middle;
      line-height: 1.4;
    }
    .export-btn:hover {
      color: var(--primary);
      border-color: var(--primary);
      background: var(--bg);
    }
    .section-header {
      margin-bottom: 20px;
    }
    .section-header h2 {
      font-size: 20px;
      font-weight: 700;
      color: var(--text);
    }
    .benchmark-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 20px;
      padding: 12px 16px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
    }
    .run-selector {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .run-selector label {
      font-size: 13px;
      color: var(--text-secondary);
      font-weight: 600;
    }
    .run-selector select {
      padding: 6px 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--bg);
      color: var(--text);
      font-size: 13px;
      max-width: 380px;
    }
    .best-badge {
      font-size: 12px;
      color: #d97706;
      font-weight: 600;
      background: #fffbeb;
      padding: 4px 10px;
      border-radius: 6px;
    }
    .benchmark-empty {
      text-align: center;
      padding: 40px;
      color: var(--text-secondary);
      background: var(--bg-card);
      border: 1px dashed var(--border);
      border-radius: 12px;
    }
    .benchmark-hint {
      display: inline-block;
      margin-top: 8px;
      padding: 6px 12px;
      background: #1e293b;
      color: #e2e8f0;
      border-radius: 6px;
      font-size: 13px;
    }
    .best-card {
      border-color: #f59e0b;
      background: linear-gradient(135deg, #fffbeb, #fff);
    }
    .best-card .summary-value {
      color: #d97706;
    }
    .benchmark-metrics {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .metric-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .metric-label {
      width: 60px;
      font-size: 11px;
      color: var(--text-secondary);
      flex-shrink: 0;
      text-align: right;
    }
    .metric-value {
      width: 45px;
      font-size: 11px;
      font-weight: 600;
      color: var(--text);
      text-align: right;
      flex-shrink: 0;
    }
    .benchmark-table-wrap {
      margin-top: 20px;
      overflow-x: auto;
    }
    .benchmark-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      background: var(--bg-card);
      border-radius: 12px;
      box-shadow: var(--shadow);
    }
    .benchmark-table th {
      background: var(--bg);
      color: var(--text-secondary);
      font-weight: 600;
      padding: 10px 8px;
      text-align: right;
      border-bottom: 1px solid var(--border);
    }
    .benchmark-table th:first-child { text-align: left; }
    .benchmark-table td {
      padding: 8px;
      text-align: right;
      border-bottom: 1px solid var(--border);
      color: var(--text);
      white-space: nowrap;
    }
    .benchmark-table td:first-child { text-align: left; }
    .best-row {
      background: #fffbeb;
    }
    .best-row td {
      font-weight: 600;
      color: #d97706;
    }
  `]
})
export class StatisticheComponent implements OnInit, OnDestroy {
  analytics: QdrantAnalyticsResponse | null = null;
  coverage: QdrantCoverageResponse | null = null;
  benchmark: BenchmarkResponse | null = null;
  benchmarkLoading = true;
  queryStats: QueryStatsResponse | null = null;
  queryStatsLoading = true;
  queryMetrics: QueryMetricsResponse | null = null;
  queryMetricsLoading = true;
  selectedRunTimestamp = '';
  selectedRun: BenchmarkFullRun | null = null;
  activeTab: 'quantitative' | 'qualitative' = 'quantitative';
  error = '';
  private sub = new Subscription();

  CHART_COLORS = [
    '#1a56db', '#16a34a', '#f59e0b', '#dc2626', '#8b5cf6',
    '#ec4899', '#06b6d4', '#f97316', '#14b8a6', '#6366f1',
  ];
  BENCH_COLORS = ['#1a56db', '#16a34a', '#f59e0b', '#dc2626', '#8b5cf6', '#ec4899', '#06b6d4'];

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
    this.sub.add(
      this.ragService.getBenchmarkResults().subscribe({
        next: (b) => {
          this.benchmark = b;
          this.benchmarkLoading = false;
          if (b.available && b.runs.length) {
            this.selectedRunTimestamp = b.runs[0].timestamp;
            this.selectedRun = b.latest;
          }
        },
        error: () => { this.benchmarkLoading = false; },
      })
    );
    this.sub.add(
      this.ragService.getQueryStats().subscribe({
        next: (qs) => { this.queryStats = qs; this.queryStatsLoading = false; },
        error: () => { this.queryStatsLoading = false; },
      })
    );
    this.sub.add(
      this.ragService.getQueryMetrics().subscribe({
        next: (qm) => { this.queryMetrics = qm; this.queryMetricsLoading = false; },
        error: () => { this.queryMetricsLoading = false; },
      })
    );
  }

  get queryCategoryData() {
    if (!this.queryStats) return [];
    const entries = Object.entries(this.queryStats.category_distribution);
    const maxVal = Math.max(...entries.map(([, v]) => v), 1);
    return entries.map(([k, v], i) => ({
      label: k, value: v, pct: (v / maxVal) * 100,
      color: this.CHART_COLORS[i % this.CHART_COLORS.length],
    }));
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

  selectRun(timestamp: string) {
    this.selectedRunTimestamp = timestamp;
    if (timestamp === this.benchmark?.runs?.[0]?.timestamp && this.benchmark?.latest) {
      this.selectedRun = this.benchmark.latest;
      return;
    }
    this.sub.add(
      this.ragService.getBenchmarkRun(timestamp).subscribe({
        next: (run) => { this.selectedRun = run; },
        error: () => {},
      })
    );
  }

  bestResult(results: BenchmarkResultItem[]): BenchmarkResultItem {
    return results.reduce((a, b) => a.metrics.mrr > b.metrics.mrr ? a : b);
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

  configTooltip(name: string): string {
    const tips: Record<string, string> = {
      'with_reranker': 'Reranker cross-encoder attivo dopo la retrieval iniziale. Migliora la precisione ma aumenta la latenza',
      'baseline': 'Configurazione standard: chunk 1500, overlap 200, hybrid search. Nessun reranker',
      'small_chunks': 'Chunk ridotti a 750 token per aumentare la granularità del retrieval',
      'large_chunks': 'Chunk grandi a 3000 token per maggiore contesto per configurazione',
      'hybrid_only': 'Sola ricerca ibrida senza reranker né ottimizzazioni aggiuntive',
      'dense_only': 'Sola embedding denso vettoriale, senza ricerca sparse (BM25)',
    };
    return tips[name] || 'Configurazione di retrieval con parametri specifici';
  }

  METRIC_IDEAL: Record<string, string> = {
    'MRR': 'Ideale > 0.80',
    'R@1': 'Ideale > 0.70',
    'R@3': 'Ideale > 0.90',
    'R@5': 'Ideale > 0.95',
    'P@1': 'Ideale > 0.70',
    'P@3': 'Ideale > 0.60',
    'ClsAcc': 'Ideale > 0.90',
  };

  refreshQueryStats() {
    this.queryStatsLoading = true;
    this.queryMetricsLoading = true;
    this.ragService.getQueryStats().subscribe({
      next: (qs) => { this.queryStats = qs; this.queryStatsLoading = false; },
      error: () => { this.queryStatsLoading = false; },
    });
    this.ragService.getQueryMetrics().subscribe({
      next: (qm) => { this.queryMetrics = qm; this.queryMetricsLoading = false; },
      error: () => { this.queryMetricsLoading = false; },
    });
  }

  exportCsv() {
    const today = new Date().toISOString().slice(0, 10);
    this.ragService.exportQueryLog().subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `query_log_${today}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
      },
      error: () => {},
    });
  }

  metricEntries(config: BenchmarkResultItem) {
    const m = config.metrics;
    const pairs = [
      { key: 'MRR', val: m.mrr },
      { key: 'R@1', val: m.recall_at_1 },
      { key: 'R@3', val: m.recall_at_3 },
      { key: 'R@5', val: m.recall_at_5 },
      { key: 'P@1', val: m.precision_at_1 },
      { key: 'P@3', val: m.precision_at_3 },
      { key: 'ClsAcc', val: m.classification_accuracy },
    ];
    const maxVal = Math.max(...pairs.map(p => p.val), 0.01);
    return pairs.map((p, i) => ({
      label: p.key,
      val: p.val.toFixed(3),
      pct: (p.val / maxVal) * 100,
      color: this.BENCH_COLORS[i % this.BENCH_COLORS.length],
      tooltip: this.METRIC_IDEAL[p.key] || '',
    }));
  }
}
