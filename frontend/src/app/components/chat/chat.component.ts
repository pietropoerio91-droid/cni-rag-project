import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RagService } from '../../services/rag.service';
import { ChatMessage } from '../../models/rag.models';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="chat-container">
      <div class="messages-area" #messagesArea>
        <div class="welcome" *ngIf="messages.length === 0">
          <h2>{{ displayTitle }}<span class="cursor-blink" *ngIf="titleTyping"></span></h2>
          <p class="welcome-text">
            Sistema di consultazione intelligente dei dati pubblici del
            <strong>Consiglio Nazionale degli Ingegneri</strong>.
            I documenti del sito <strong>www.cni.it</strong> sono indicizzati
            e interrogabili tramite intelligenza artificiale.
          </p>
          <div class="stats-bar" *ngIf="stats">
            <span class="stat-item">
              <strong>{{ stats.docs }}</strong> documenti indicizzati
            </span>
            <span class="stat-sep"></span>
            <span class="stat-item">
              <strong>{{ stats.categories }}</strong> categorie
            </span>
            <span class="stat-sep"></span>
            <span class="stat-item">
              <strong>{{ stats.sources }}</strong> fonti
            </span>
          </div>
          <p class="welcome-tip">{{ currentTip }}</p>
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
    .welcome h2 {
      font-size: 22px;
      font-weight: 600;
      margin-bottom: 12px;
      color: var(--text);
      min-height: 28px;
    }
    .cursor-blink {
      display: inline-block;
      width: 2px;
      height: 22px;
      background: var(--primary);
      margin-left: 2px;
      vertical-align: middle;
      animation: blink 0.7s step-end infinite;
    }
    @keyframes blink {
      50% { opacity: 0; }
    }
    .welcome-text {
      color: var(--text-secondary);
      font-size: 15px;
      line-height: 1.7;
      margin-bottom: 20px;
    }
    .welcome-text-secondary {
      color: var(--text-secondary);
      font-size: 14px;
      line-height: 1.6;
      margin-bottom: 32px;
    }
    .stats-bar {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0;
      margin-bottom: 20px;
      font-size: 13px;
      color: var(--text-secondary);
    }
    .stat-item strong {
      color: var(--primary);
    }
    .stat-sep {
      width: 1px;
      height: 24px;
      background: var(--border);
      margin: 0 16px;
    }
    .welcome-tip {
      color: var(--text-secondary);
      font-size: 13px;
      font-style: italic;
      margin-bottom: 24px;
      min-height: 20px;
      transition: opacity 0.3s;
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
      width: 10px;
      height: 10px;
      background: var(--text-secondary);
      border-radius: 50%;
      animation: typing 1.4s infinite ease-in-out;
    }
    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes typing {
      0%, 60%, 100% { transform: translateY(0); opacity: 0.6; }
      30% { transform: translateY(-10px); opacity: 1; }
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
  `]
})
export class ChatComponent implements OnInit, OnDestroy {
  messages: ChatMessage[] = [];
  currentQuestion = '';
  isLoading = false;
  stats: { docs: number; categories: number; sources: number } | null = null;
  currentTip = 'Prova a chiedere "Quali servizi offre il CNI?" per iniziare';
  displayTitle = '';
  titleTyping = true;
  private tipInterval: ReturnType<typeof setInterval> | null = null;
  private sub = new Subscription();

  tips = [
    'Prova a chiedere "Quali sono gli organi del CNI?" per iniziare',
    'Puoi fare domande su formazione, servizi e sicurezza sul lavoro',
    'Le risposte includono citazioni con link ai documenti originali',
    'Chiedi "Che cos\'è un near miss?" per temi di sicurezza sul lavoro',
    'I documenti provengono dal sito ufficiale www.cni.it',
    'Prova "Quali servizi offre il CNI?" per scoprire i servizi agli ingegneri',
  ];

  suggestions = [
    'Quali sono gli organi del CNI?',
    'Quali servizi offre il CNI?',
    'Come funziona la formazione continua?',
    'Che cos\'è un near miss per la sicurezza?',
    'Chi è il presidente del CNI?',
    'Quali sono i temi trattati dal CNI?',
  ];

  constructor(private ragService: RagService) {}

  ngOnInit() {
    this.typeTitle();
    this.tipInterval = setInterval(() => this.nextTip(), 6000);
    this.sub.add(
      this.ragService.getQdrantAnalytics().subscribe({
        next: (a) => {
          this.stats = {
            docs: a.total_documents,
            categories: Object.keys(a.categories).length,
            sources: a.top_sources.length,
          };
        },
      })
    );
    this.sub.add(
      this.ragService.chatReset$.subscribe(() => {
        this.resetHome();
        this.typeTitle();
      })
    );
  }

  private typeTitle() {
    const text = 'Benvenuto';
    let i = 0;
    const interval = setInterval(() => {
      if (i < text.length) {
        this.displayTitle += text[i];
        i++;
      } else {
        clearInterval(interval);
        this.titleTyping = false;
      }
    }, 50);
  }

  ngOnDestroy() {
    if (this.tipInterval) clearInterval(this.tipInterval);
    this.sub.unsubscribe();
  }

  private nextTip() {
    const available = this.tips.filter(t => t !== this.currentTip);
    this.currentTip = available[Math.floor(Math.random() * available.length)];
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

    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      timestamp: new Date(),
    };
    this.messages.push(assistantMsg);
    this.isLoading = true;

    this.ragService.query({ question }).subscribe({
      next: (response) => {
        assistantMsg.content = response.response;
        assistantMsg.citations = response.citations;
        assistantMsg.category = response.category;
        this.isLoading = false;
        this.scrollToBottom();
      },
      error: (err) => {
        assistantMsg.content = `❌ Errore: ${err.message}`;
        assistantMsg.error = true;
        this.isLoading = false;
        this.scrollToBottom();
      },
    });
  }

  resetHome() {
    this.messages = [];
    this.currentQuestion = '';
    this.isLoading = false;
  }

  private scrollToBottom() {
    setTimeout(() => {
      const area = document.querySelector('.messages-area');
      if (area) area.scrollTop = area.scrollHeight;
    }, 50);
  }
}
