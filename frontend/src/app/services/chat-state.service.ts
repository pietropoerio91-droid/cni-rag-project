import { Injectable } from '@angular/core';
import { ChatMessage } from '../models/rag.models';

/**
 * Stato della chat condiviso a livello di applicazione (singleton, root
 * injector). Il router Angular distrugge e ricrea ChatComponent quando si
 * naviga verso un'altra rotta (es. /statistiche) e si torna indietro: senza
 * questo servizio lo storico dei messaggi viveva nel componente e andava
 * perso a ogni cambio pagina.
 */
@Injectable({ providedIn: 'root' })
export class ChatStateService {
  messages: ChatMessage[] = [];
  currentQuestion = '';
  isLoading = false;

  reset(): void {
    this.messages = [];
    this.currentQuestion = '';
    this.isLoading = false;
  }
}
