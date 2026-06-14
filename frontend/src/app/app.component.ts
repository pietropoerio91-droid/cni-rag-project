import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChatComponent } from './components/chat/chat.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, ChatComponent],
  template: `
    <div class="app-layout">
      <header class="app-header">
        <div class="header-content">
          <h1 class="app-title">CNI RAG</h1>
          <span class="app-subtitle">Consulenza Dati Pubblici</span>
          <div class="header-status">
            <span class="status-dot" [class.active]="apiConnected"></span>
            <span class="status-text">{{ apiConnected ? 'Connesso' : 'Disconnesso' }}</span>
          </div>
        </div>
      </header>
      <main class="app-main">
        <app-chat (apiStatusChange)="onApiStatusChange($event)"></app-chat>
      </main>
    </div>
  `,
  styles: [`
    .app-layout {
      display: flex;
      flex-direction: column;
      height: 100vh;
    }
    .app-header {
      background: var(--bg-card);
      border-bottom: 1px solid var(--border);
      padding: 0 24px;
      flex-shrink: 0;
    }
    .header-content {
      max-width: 1200px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      gap: 16px;
      height: 60px;
    }
    .app-title {
      font-size: 18px;
      font-weight: 700;
      color: var(--primary);
    }
    .app-subtitle {
      font-size: 13px;
      color: var(--text-secondary);
      flex: 1;
    }
    .header-status {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: var(--text-secondary);
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--error);
    }
    .status-dot.active {
      background: var(--success);
    }
    .app-main {
      flex: 1;
      overflow: hidden;
    }
  `]
})
export class AppComponent {
  apiConnected = false;

  onApiStatusChange(connected: boolean) {
    this.apiConnected = connected;
  }
}
