import { Component, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChatComponent } from './components/chat/chat.component';
import { RagService } from './services/rag.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, ChatComponent],
  template: `
    <div class="app-layout">
      <header class="app-header">
        <div class="header-content">
          <div class="header-brand" (click)="goHome()" title="Torna alla home">
            <div class="brand-text">
              <span class="brand-title">Consiglio Nazionale degli Ingegneri</span>
              <span class="brand-subtitle">Consultazione dati pubblici</span>
            </div>
          </div>
          <div class="header-actions">
            <div class="dropdown" #dropdown>
              <button class="icon-btn" (click)="toggleMenu()" title="Impostazioni">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="3"></circle>
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                </svg>
              </button>
              <div class="dropdown-menu" *ngIf="menuOpen">
                <div class="menu-item">
                  <span class="status-dot" [class.active]="apiConnected"></span>
                  <span>{{ apiConnected ? 'Connesso' : 'Disconnesso' }}</span>
                  <span class="tip-trigger" data-tip="Stato di connessione al server e al modello di intelligenza artificiale">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                  </span>
                </div>
                <div class="menu-item">
                  <span>📄 <strong>{{ documentsIndexed }}</strong> chunk indicizzati</span>
                  <span class="tip-trigger" data-tip="Totale documenti processati e pronti per essere interrogati">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                  </span>
                </div>
                <div class="menu-item" *ngIf="lastIndexingDate">
                  <span>📅 {{ documentsIndexed }} chunk al {{ lastIndexingDate | date:'dd/MM/yyyy' }}</span>
                  <span class="tip-trigger" data-tip="Data dell'ultimo aggiornamento dei dati nel sistema">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                  </span>
                </div>
                <div class="menu-divider"></div>
                <button class="menu-item action" (click)="ingestData()" [disabled]="isIngesting">
                  <span>{{ isIngesting ? '⏳ Indicizzazione...' : '📥 Indicizza Dati' }}</span>
                  <span class="tip-trigger" (click)="$event.stopPropagation()" data-tip="Scarica e indicizza i documenti pubblici dal sito cni.it per mantenerli aggiornati">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                  </span>
                </button>
                <button class="menu-item action" (click)="checkHealth()">
                  <span>🔄 Verifica Connessione</span>
                  <span class="tip-trigger" (click)="$event.stopPropagation()" data-tip="Verifica che il sistema sia operativo e pronto a rispondere alle domande">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                  </span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>
      <main class="app-main">
        <app-chat></app-chat>
      </main>
    </div>
  `,
  host: {
    '(document:click)': 'onDocumentClick($event)',
  },
  styles: [`
    .app-layout {
      display: flex;
      flex-direction: column;
      height: 100vh;
    }
    .app-header {
      background: var(--bg-card);
      border-bottom: 1px solid var(--border);
      padding: 0 16px;
      flex-shrink: 0;
    }
    .header-content {
      max-width: 1200px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      gap: 12px;
      height: 60px;
    }
    .icon-btn {
      width: 36px;
      height: 36px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--text-secondary);
      transition: background 0.2s;
      flex-shrink: 0;
    }
    .icon-btn:hover {
      background: var(--bg);
    }
    .header-brand {
      flex: 1;
      display: flex;
      align-items: center;
      min-width: 0;
      cursor: pointer;
    }
    .brand-text {
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .brand-title {
      font-size: 15px;
      font-weight: 600;
      color: var(--text);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .brand-subtitle {
      font-size: 12px;
      color: var(--text-secondary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .header-actions {
      position: relative;
      flex-shrink: 0;
    }
    .dropdown-menu {
      position: absolute;
      right: 0;
      top: 100%;
      margin-top: 8px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 10px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.1);
      min-width: 230px;
      padding: 6px;
      z-index: 100;
    }
    .menu-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 13px;
      color: var(--text-secondary);
    }
    .menu-item.action {
      width: 100%;
      text-align: left;
      cursor: pointer;
      transition: background 0.15s;
      color: var(--text);
    }
    .menu-item.action:hover:not(:disabled) {
      background: var(--bg);
    }
    .menu-item.action:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .menu-divider {
      height: 1px;
      background: var(--border);
      margin: 4px 0;
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--error);
      flex-shrink: 0;
    }
    .status-dot.active {
      background: var(--success);
    }
    .tip-trigger {
      position: relative;
      display: inline-flex;
      align-items: center;
      color: var(--text-secondary);
      cursor: help;
      flex-shrink: 0;
      margin-left: auto;
      opacity: 0.4;
      transition: opacity 0.15s;
    }
    .tip-trigger:hover {
      opacity: 1;
    }
    .tip-trigger::after {
      content: attr(data-tip);
      position: absolute;
      right: 0;
      bottom: calc(100% + 8px);
      background: #1e293b;
      color: #fff;
      font-size: 12px;
      line-height: 1.4;
      padding: 8px 12px;
      border-radius: 8px;
      white-space: normal;
      width: 240px;
      pointer-events: none;
      opacity: 0;
      transform: translateY(4px);
      transition: opacity 0.2s, transform 0.2s;
      box-shadow: 0 4px 12px rgba(0,0,0,0.2);
      z-index: 200;
    }
    .tip-trigger:hover::after {
      opacity: 1;
      transform: translateY(0);
    }
    .app-main {
      flex: 1;
      overflow: hidden;
    }
  `]
})
export class AppComponent implements OnInit {
  @ViewChild(ChatComponent) chatComponent!: ChatComponent;

  apiConnected = false;
  documentsIndexed = 0;
  lastIndexingDate: Date | null = null;
  lastCheck: Date | null = null;
  menuOpen = false;
  isIngesting = false;

  constructor(private ragService: RagService) {}

  goHome() {
    this.chatComponent?.resetHome();
  }

  ngOnInit() {
    this.checkHealth();
  }

  toggleMenu() {
    this.menuOpen = !this.menuOpen;
  }

  checkHealth() {
    this.ragService.health().subscribe({
      next: (health) => {
        this.apiConnected = health.llm_connected && health.status === 'ok';
        this.documentsIndexed = health.documents_indexed;
        this.lastCheck = new Date();
      },
      error: () => {
        this.apiConnected = false;
        this.lastCheck = new Date();
      },
    });
  }

  ingestData() {
    this.isIngesting = true;
    this.menuOpen = false;
    this.ragService.ingest().subscribe({
      next: (response) => {
        this.isIngesting = false;
        this.documentsIndexed = response.chunks_indexed;
        this.lastIndexingDate = new Date();
        this.checkHealth();
      },
      error: () => {
        this.isIngesting = false;
      },
    });
  }

  onDocumentClick(event: MouseEvent) {
    if (this.menuOpen) {
      const target = event.target as HTMLElement;
      if (!target.closest('.dropdown')) {
        this.menuOpen = false;
      }
    }
  }
}
