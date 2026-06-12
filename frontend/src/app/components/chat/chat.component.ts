import { Component, EventEmitter, OnInit, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RagService } from '../../services/rag.service';
import { ChatMessage } from '../../models/rag.models';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="chat-container">
      <div class="messages-area" #messagesArea>
        <div class="welcome" *ngIf="messages.length === 0">
          <div class="welcome-icon">🏛️</div>
          <h2>Consulta i dati pubblici del CNI</h2>
          <p class="welcome-text">
            Fai una domanda su normativa, organi, commissioni, formazione e altri dati pubblici
            del Consiglio Nazionale degli Ingegneri.
          </p>
          <div class="suggestions">
            <button class="suggestion-chip" *ngFor="let s of suggestions" (click)="sendQuestion(s)">
              {{ s }}
            </button>
          </div>
        </div>

        <div class="message" *ngFor="let msg of messages" [class.user]="msg.role === 'user'" [class.error]="msg.error">
          <div class="message-bubble">
            <div class="message-header">
              <span class="message-role">{{ msg.role === 'user' ? 'Tu' : 'CNI Assistant' }}</span>
              <span class="message-time">{{ msg.timestamp | date:'HH:mm' }}</span>
            </div>
            <div class="message-content" [innerHTML]="msg.content"></div>
            <div class="message-citations" *ngIf="msg.citations && msg.citations.length > 0">
              <div class="citation" *ngFor="let c of msg.citations">
                <span class="citation-icon">📄</span>
                <a [href]="c.source" target="_blank" class="citation-link">{{ c.title }}</a>
                <span class="citation-score">({{ (c.relevance_score * 100).toFixed(0) }}%)</span>
              </div>
            </div>
          </div>
        </div>

        <div class="typing-indicator" *ngIf="isLoading">
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
        </div>
      </div>

      <div class="input-area">
        <div class="input-wrapper">
          <textarea
            class="question-input"
            [(ngModel)]="currentQuestion"
            (keydown.enter)="onEnter($event)"
            placeholder="Fai una domanda sul CNI..."
            rows="1"
            [disabled]="isLoading"
          ></textarea>
          <button
            class="send-button"
            (click)="sendMessage()"
            [disabled]="!currentQuestion.trim() || isLoading"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
            </svg>
          </button>
        </div>
        <div class="input-footer">
          <button class="action-button" (click)="checkHealth()" title="Stato connessione">
            <span class="status-led" [class.online]="apiOnline"></span>
            {{ apiOnline ? 'API Online' : 'API Offline' }}
          </button>
          <button class="action-button" (click)="ingestData()" [disabled]="isLoading" title="Importa dati CNI">
            📥 Indicizza Dati
          </button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .chat-container {
      display: flex;
      flex-direction: column;
      height: 100%;
      max-width: 900px;
      margin: 0 auto;
    }
    .messages-area {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      scroll-behavior: smooth;
    }
    .welcome {
      text-align: center;
      padding: 60px 24px;
      max-width: 600px;
      margin: 0 auto;
    }
    .welcome-icon {
      font-size: 48px;
      margin-bottom: 16px;
    }
    .welcome h2 {
      font-size: 22px;
      font-weight: 600;
      margin-bottom: 12px;
      color: var(--text);
    }
    .welcome-text {
      color: var(--text-secondary);
      font-size: 15px;
      line-height: 1.7;
      margin-bottom: 32px;
    }
    .suggestions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: center;
    }
    .suggestion-chip {
      background: var(--primary-light);
      color: var(--primary);
      padding: 8px 16px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 500;
      transition: background 0.2s;
    }
    .suggestion-chip:hover {
      background: #bfdbfe;
    }
    .message {
      display: flex;
      margin-bottom: 16px;
    }
    .message.user {
      justify-content: flex-end;
    }
    .message-bubble {
      max-width: 80%;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 16px;
      box-shadow: var(--shadow);
    }
    .message.user .message-bubble {
      background: var(--primary);
      color: white;
      border-color: var(--primary);
    }
    .message.error .message-bubble {
      border-color: var(--error);
      background: #fef2f2;
    }
    .message-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
    }
    .message-role {
      font-weight: 600;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      opacity: 0.8;
    }
    .message-time {
      font-size: 11px;
      opacity: 0.6;
    }
    .message-content {
      line-height: 1.7;
      white-space: pre-wrap;
    }
    .message.user .message-content {
      color: white;
    }
    .message-citations {
      margin-top: 12px;
      padding-top: 10px;
      border-top: 1px solid var(--border);
    }
    .message.user .message-citations {
      border-color: rgba(255,255,255,0.2);
    }
    .citation {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      padding: 4px 0;
    }
    .citation-icon {
      flex-shrink: 0;
    }
    .citation-link {
      color: var(--primary);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 250px;
    }
    .message.user .citation-link {
      color: #93c5fd;
    }
    .citation-score {
      color: var(--text-secondary);
      font-size: 11px;
      flex-shrink: 0;
    }
    .typing-indicator {
      display: flex;
      gap: 4px;
      padding: 12px 16px;
    }
    .typing-dot {
      width: 8px;
      height: 8px;
      background: var(--border);
      border-radius: 50%;
      animation: typing 1.4s infinite ease-in-out;
    }
    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes typing {
      0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
      30% { transform: translateY(-8px); opacity: 1; }
    }
    .input-area {
      border-top: 1px solid var(--border);
      background: var(--bg-card);
      padding: 12px 24px 16px;
    }
    .input-wrapper {
      display: flex;
      gap: 8px;
      align-items: flex-end;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 8px 8px 8px 16px;
      transition: border-color 0.2s;
    }
    .input-wrapper:focus-within {
      border-color: var(--primary);
    }
    .question-input {
      flex: 1;
      border: none;
      background: transparent;
      resize: none;
      font-size: 14px;
      line-height: 1.5;
      max-height: 120px;
      outline: none;
      color: var(--text);
    }
    .send-button {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: var(--primary);
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.2s;
      flex-shrink: 0;
    }
    .send-button:hover:not(:disabled) {
      background: var(--primary-dark);
    }
    .send-button:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }
    .input-footer {
      display: flex;
      gap: 12px;
      margin-top: 8px;
      padding-left: 4px;
    }
    .action-button {
      font-size: 12px;
      color: var(--text-secondary);
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 4px 8px;
      border-radius: 6px;
      transition: background 0.2s;
    }
    .action-button:hover:not(:disabled) {
      background: var(--bg);
    }
    .action-button:disabled {
      opacity: 0.4;
    }
    .status-led {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--error);
    }
    .status-led.online {
      background: var(--success);
    }
  `]
})
export class ChatComponent implements OnInit {
  @Output() apiStatusChange = new EventEmitter<boolean>();

  messages: ChatMessage[] = [];
  currentQuestion = '';
  isLoading = false;
  apiOnline = false;

  suggestions = [
    'Quali sono gli organi del CNI?',
    'Cosa dice la normativa per gli ingegneri?',
    'Come funziona la formazione continua?',
    'Quali commissioni esistono?',
  ];

  constructor(private ragService: RagService) {}

  ngOnInit() {
    this.checkHealth();
  }

  onEnter(event: Event) {
    const keyboardEvent = event as KeyboardEvent;
    if (!keyboardEvent.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  sendMessage() {
    if (!this.currentQuestion.trim() || this.isLoading) return;
    this.sendQuestion(this.currentQuestion.trim());
    this.currentQuestion = '';
  }

  sendQuestion(question: string) {
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: question,
      timestamp: new Date(),
    };
    this.messages.push(userMsg);
    this.isLoading = true;

    this.ragService.query({ question }).subscribe({
      next: (response) => {
        const assistantMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.response,
          citations: response.citations,
          category: response.category,
          timestamp: new Date(),
        };
        this.messages.push(assistantMsg);
        this.isLoading = false;
        this.scrollToBottom();
      },
      error: (err) => {
        const errorMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `❌ Errore: ${err.message}`,
          error: true,
          timestamp: new Date(),
        };
        this.messages.push(errorMsg);
        this.isLoading = false;
        this.scrollToBottom();
      },
    });
  }

  checkHealth() {
    this.ragService.health().subscribe({
      next: (health) => {
        this.apiOnline = health.llm_connected && health.status === 'ok';
        this.apiStatusChange.emit(this.apiOnline);
      },
      error: () => {
        this.apiOnline = false;
        this.apiStatusChange.emit(false);
      },
    });
  }

  ingestData() {
    this.isLoading = true;
    const msg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '⏳ Avvio indicizzazione dati CNI...',
      timestamp: new Date(),
    };
    this.messages.push(msg);

    this.ragService.ingest().subscribe({
      next: (response) => {
        msg.content = `✅ Indicizzazione completata!\n\n- Documenti processati: ${response.documents_crawled}\n- Chunk indicizzati: ${response.chunks_indexed}\n- ${response.message}`;
        this.isLoading = false;
      },
      error: (err) => {
        msg.content = `❌ Errore indicizzazione: ${err.message}`;
        msg.error = true;
        this.isLoading = false;
      },
    });
  }

  private scrollToBottom() {
    setTimeout(() => {
      const area = document.querySelector('.messages-area');
      if (area) area.scrollTop = area.scrollHeight;
    }, 50);
  }
}
