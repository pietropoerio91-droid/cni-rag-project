import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RagService } from '../../services/rag.service';
import {
  AgreementReport,
  AnnotationItem,
  AnnotationQueue,
  EvaluationLatest,
  EvaluationRunSummary,
  MetricCI,
} from '../../models/rag.models';

/**
 * Tab qualitativa — valutazione sul golden dataset.
 *
 * Sostituisce le metriche che l'API calcolava sulle query degli utenti: quelle
 * definivano la rilevanza come "score > soglia", cioè dal punteggio del
 * retriever stesso, e non erano quindi metriche di Information Retrieval.
 * Le query in produzione non hanno fonti attese note; le metriche vere si
 * calcolano solo sul golden dataset.
 *
 * Quattro viste:
 *   Risultati      metriche del run con intervalli di confidenza al 95%
 *   Annotazione    valutazione umana IN CIECO, senza vedere i voti del giudice
 *   Corrispondenza accordo umano-giudice (kappa pesato, alfa, matrice)
 *   Per domanda    dove si perde la risposta, stadio per stadio
 */
@Component({
  selector: 'app-valutazione',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="val">

      <!-- selettore del run -->
      <div class="topbar" *ngIf="runs.length">
        <label>Run</label>
        <select [(ngModel)]="runIdSelezionato" (change)="caricaTutto()">
          <option *ngFor="let r of runs" [value]="r.run_id">
            {{ r.run_id }} — {{ r.total_questions }} domande — {{ r.run_date | date:'dd/MM HH:mm' }}
          </option>
        </select>
        <a class="btn-ghost" [href]="csvUrl()" download>Esporta CSV</a>
      </div>

      <div class="tabs2">
        <button *ngFor="let v of viste" class="t2" [class.on]="vista === v.id" (click)="vista = v.id">
          {{ v.label }}
          <span class="badge" *ngIf="v.id === 'annota' && coda">{{ coda.annotate }}/{{ coda.totale }}</span>
        </button>
      </div>

      <div class="loading" *ngIf="caricando"><div class="spin"></div></div>
      <div class="err" *ngIf="errore">{{ errore }}</div>

      <!-- ================= RISULTATI ================= -->
      <ng-container *ngIf="vista === 'risultati' && latest && !caricando">
        <div class="warn" *ngIf="accordo && accordo.giudice_utilizzabile === false">
          <b>Giudice automatico: accordo con l'annotazione umana sotto soglia
             (κ medio {{ accordo.kappa_medio | number:'1.3-3' }}, soglia ≥ 0,61).</b>
          {{ accordo.conclusione }} Dettaglio per metrica nella tab «Corrispondenza».
        </div>

        <div class="meta">
          <span><b>{{ latest.total_questions }}</b> domande</span>
          <span>dataset <b>{{ latest.dataset_version || latest.dataset }}</b></span>
          <span>giudice <b>{{ latest.judge_model || '—' }}</b></span>
          <span>latenza media <b>{{ latest.avg_latency_s }} s</b></span>
        </div>

        <h3>Retrieval — prima e dopo il reranking</h3>
        <p class="hint">
          «candidati» è ciò che produce il retriever denso; «contesto» è ciò che l'LLM
          riceve davvero dopo il reranking. È il secondo che conta.
        </p>
        <table class="tab">
          <thead>
            <tr>
              <th>Metrica</th><th>Candidati</th><th>Contesto</th>
              <th>Effetto del reranker
                <span class="tooltip-wrap table-tip">
                  <span class="tooltip-icon">i</span>
                  <span class="tooltip-text">Differenza contesto − candidati, con p-value del test a coppie
                    e magnitudine del delta di Cliff. «sig» solo se p &lt; 0,05.</span>
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let k of metricheRetrieval">
              <td>
                {{ etichettaRetrieval(k) }}
                <span class="tooltip-wrap table-tip">
                  <span class="tooltip-icon">i</span>
                  <span class="tooltip-text">{{ descrizioneRetrieval(k) }}</span>
                </span>
              </td>
              <td>{{ fmtCI(ci('retrieved', k), isPct(k)) }}</td>
              <td class="strong">{{ fmtCI(ci('context', k), isPct(k)) }}</td>
              <td>
                <span *ngIf="eff(k) as e" [class.sig]="e.significance.p_value < 0.05">
                  {{ e.mean_difference > 0 ? '+' : '' }}{{ e.mean_difference | number:'1.3-3' }}
                  <small>p={{ e.significance.p_value | number:'1.4-4' }} · {{ e.effect_size.magnitude }}</small>
                </span>
                <span *ngIf="!eff(k)" class="dim">—</span>
              </td>
            </tr>
          </tbody>
        </table>

        <h3>Generazione</h3>
        <table class="tab">
          <tbody>
            <tr>
              <td>Must-contain superato <small class="dim">(deterministico)</small></td>
              <td class="strong">{{ pct(gen('must_contain_pass_rate')) }}</td>
            </tr>
            <tr>
              <td>Fallback attivato</td>
              <td>{{ pct(latest.fallback_rate) }}
                <small class="dim" *ngIf="latest.fallback_rate_ci">
                  [{{ pct(latest.fallback_rate_ci[0]) }}, {{ pct(latest.fallback_rate_ci[1]) }}]
                </small>
              </td>
            </tr>
            <tr *ngFor="let m of metricheGiudice" [class.unvalidated]="metricaAffidabile(m) !== true">
              <td>{{ etichetta(m) }} <small class="dim">(giudice 0-5)</small></td>
              <td>{{ fmtCI(ciGen(m), false) }}
                <small class="flag" *ngIf="metricaAffidabile(m) === false">
                  sotto soglia — κ={{ acc(m)?.kappa_quadratico | number:'1.3-3' }}
                </small>
                <small class="flag" *ngIf="metricaAffidabile(m) === null">accordo non ancora calcolato</small>
              </td>
            </tr>
          </tbody>
        </table>
      </ng-container>

      <!-- ================= ANNOTAZIONE ================= -->
      <ng-container *ngIf="vista === 'annota' && coda && !caricando">

        <div class="stale" *ngIf="coda.disallineato">
          <div class="stale-h">Le risposte di questo run non sono aggiornate</div>
          <p>{{ coda.avviso_disallineamento }}</p>
          <p class="stale-w">
            Annotare risposte che il sistema non produce più significa misurare
            qualcosa che non esiste. Esegui un nuovo run end-to-end e annota quello.
          </p>
          <button class="btn-ghost" (click)="ignoraDisallineamento = true"
                  *ngIf="!ignoraDisallineamento">Annota lo stesso</button>
        </div>

        <ng-container *ngIf="!coda.disallineato || ignoraDisallineamento">
        <div class="progress">
          <div class="bar"><i [style.width.%]="coda.totale ? 100 * coda.annotate / coda.totale : 0"></i></div>
          <span>{{ coda.annotate }} di {{ coda.totale }} annotate · ne mancano {{ coda.mancanti }}</span>
        </div>

        <div class="blind" *ngIf="coda.blind">
          Annotazione in cieco: i voti del giudice non sono mostrati, per non influenzare il tuo giudizio.
        </div>

        <div class="card" *ngIf="corrente as it">
          <div class="navrow">
            <button (click)="vai(-1)" [disabled]="indice === 0">←</button>
            <span class="qid">{{ it.question_id }} <small>({{ indice + 1 }}/{{ coda.items.length }})</small></span>
            <button (click)="vai(1)" [disabled]="indice >= coda.items.length - 1">→</button>
            <button class="btn-ghost" (click)="prossimaNonAnnotata()">Prossima da fare</button>
          </div>

          <div class="q">{{ it.question }}</div>
          <div class="chips">
            <span class="chip">{{ it.category }}</span>
            <span class="chip" [class.bad]="it.must_contain_pass === false"
                  [class.good]="it.must_contain_pass === true"
                  *ngIf="it.must_contain_pass !== null">
              must-contain {{ it.must_contain_pass ? 'superato' : 'fallito' }}
            </span>
            <span class="chip" *ngIf="it.rank_pre_rerank">rank candidati {{ it.rank_pre_rerank }}</span>
            <span class="chip" [class.bad]="!it.rank_post_rerank">
              rank contesto {{ it.rank_post_rerank || 'assente' }}
            </span>
            <span class="chip bad" *ngIf="it.fallback_triggered">fallback</span>
          </div>

          <div class="pane">
            <div class="pane-t">Risposta del sistema</div>
            <div class="pane-b">{{ it.response }}</div>
          </div>
          <div class="pane">
            <div class="pane-t">Risposta di riferimento <small>(verità nota)</small></div>
            <div class="pane-b ref">{{ it.reference_answer }}</div>
          </div>
          <div class="pane" *ngIf="it.context_sources?.length">
            <div class="pane-t">Documenti passati all'LLM</div>
            <ol class="srcs">
              <li *ngFor="let s of it.context_sources"
                  [class.hit]="combacia(s, it.expected_sources)">{{ s }}</li>
            </ol>
          </div>

          <div class="scores">
            <div class="srow" *ngFor="let m of coda.metriche">
              <div class="slab">
                {{ etichetta(m) }}
                <small>{{ descrizione(m) }}</small>
              </div>
              <div class="sbtns">
                <button *ngFor="let v of [0,1,2,3,4,5]"
                        [class.sel]="voti[m] === v"
                        (click)="voti[m] = v">{{ v }}</button>
                <button class="clr" (click)="voti[m] = null" title="azzera">×</button>
              </div>
            </div>

            <div class="srow">
              <div class="slab">Stadio dell'errore
                <small>dove si è persa la risposta</small>
              </div>
              <select [(ngModel)]="stadio">
                <option [ngValue]="null">— non codificato —</option>
                <option *ngFor="let s of stadiKeys" [value]="s">{{ coda.stadi_errore[s] }}</option>
              </select>
            </div>

            <div class="srow">
              <div class="slab">Note</div>
              <input type="text" [(ngModel)]="nota" placeholder="facoltativo">
            </div>
          </div>

          <div class="actions">
            <button class="btn" (click)="salva(true)" [disabled]="salvando">
              {{ salvando ? 'Salvo…' : 'Salva e vai avanti' }}
            </button>
            <button class="btn-ghost" (click)="salva(false)" [disabled]="salvando">Salva e resta</button>
            <span class="saved" *ngIf="messaggio">{{ messaggio }}</span>
          </div>
        </div>
        </ng-container>
      </ng-container>

      <!-- ================= CORRISPONDENZA ================= -->
      <ng-container *ngIf="vista === 'accordo' && accordo && !caricando">
        <div class="verdict" [class.ko]="accordo.giudice_utilizzabile === false"
                             [class.ok]="accordo.giudice_utilizzabile === true">
          <div class="vnum" *ngIf="accordo.kappa_medio !== null">
            κ = {{ accordo.kappa_medio | number:'1.3-3' }}
          </div>
          <div class="vnum dim" *ngIf="accordo.kappa_medio === null">κ = —</div>
          <div class="vtxt">
            <b *ngIf="accordo.interpretazione_complessiva">
              Accordo {{ accordo.interpretazione_complessiva }}
            </b>
            <p>{{ accordo.conclusione }}</p>
            <p class="dim">
              {{ accordo.n_domande_confrontabili }} domande confrontabili su
              {{ accordo.totale_domande_run }} · giudice: {{ accordo.judge_model }}
              <span class="flag" *ngIf="accordo.giudice_uguale_al_generatore">
                stesso modello del generatore — bias di autovalutazione
              </span>
            </p>
          </div>
        </div>

        <table class="tab" *ngIf="accordo.n_domande_confrontabili">
          <thead>
            <tr>
              <th>Metrica</th><th>n</th><th>media umano</th><th>media giudice</th>
              <th>bias
                <span class="tooltip-wrap table-tip">
                  <span class="tooltip-icon">i</span>
                  <span class="tooltip-text">Media giudice − media umano. Positivo: il giudice è più
                    generoso dell'umano; negativo: più severo.</span>
                </span>
              </th>
              <th>MAE
                <span class="tooltip-wrap table-tip">
                  <span class="tooltip-icon">i</span>
                  <span class="tooltip-text">Errore assoluto medio fra voto giudice e voto umano,
                    in punti sulla scala 0-5.</span>
                </span>
              </th>
              <th>entro 1
                <span class="tooltip-wrap table-tip">
                  <span class="tooltip-icon">i</span>
                  <span class="tooltip-text">Quota di domande in cui giudice e umano si discostano
                    al massimo di 1 punto.</span>
                </span>
              </th>
              <th>κ pesato
                <span class="tooltip-wrap table-tip">
                  <span class="tooltip-icon">i</span>
                  <span class="tooltip-text">Kappa di Cohen, pesi quadratici: accordo corretto per il
                    caso. Sotto 0,61 il giudice non è considerato utilizzabile in questo lavoro.</span>
                </span>
              </th>
              <th>α Kripp.
                <span class="tooltip-wrap table-tip">
                  <span class="tooltip-icon">i</span>
                  <span class="tooltip-text">Alfa di Krippendorff: misura di affidabilità alternativa
                    al kappa, meno sensibile alla distribuzione dei voti.</span>
                </span>
              </th>
              <th>r Pearson
                <span class="tooltip-wrap table-tip">
                  <span class="tooltip-icon">i</span>
                  <span class="tooltip-text">Correlazione lineare fra i due punteggi: resta alta
                    anche se il giudice sbaglia sempre nella stessa direzione — non implica accordo.</span>
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let m of metricheGiudice">
              <td>{{ etichetta(m) }}</td>
              <td>{{ acc(m)?.n }}</td>
              <td>{{ acc(m)?.media_umano | number:'1.2-2' }}</td>
              <td>{{ acc(m)?.media_giudice | number:'1.2-2' }}</td>
              <td [class.sig]="abs(acc(m)?.bias_giudice) > 0.5">
                {{ acc(m)?.bias_giudice | number:'1.2-2' }}
              </td>
              <td>{{ acc(m)?.mae | number:'1.2-2' }}</td>
              <td>{{ pct(acc(m)?.accordo_entro_1) }}</td>
              <td class="strong">{{ acc(m)?.kappa_quadratico | number:'1.3-3' }}
                <small class="dim">{{ acc(m)?.interpretazione_kappa }}</small>
              </td>
              <td>{{ acc(m)?.krippendorff_alpha | number:'1.3-3' }}</td>
              <td>{{ acc(m)?.pearson_r | number:'1.2-2' }}</td>
            </tr>
          </tbody>
        </table>

        <p class="hint" *ngIf="accordo.n_domande_confrontabili">
          κ pesato (pesi quadratici) e α di Krippendorff correggono per l'accordo dovuto al caso:
          sono le misure da riportare. MAE e «entro 1» sono descrittivi. Pearson dice se i due
          valutatori ordinano allo stesso modo, non se concordano — un giudice che sbaglia di 3
          punti sempre nella stessa direzione ha r = 1.
        </p>

        <div class="matrici" *ngIf="accordo.n_domande_confrontabili">
          <div class="mat" *ngFor="let m of metricheGiudice">
            <h4>{{ etichetta(m) }}</h4>
            <table class="cm" *ngIf="acc(m)?.matrice_confusione as mat">
              <tr><td class="cnr"></td><td class="ch" *ngFor="let c of [0,1,2,3,4,5]">{{ c }}</td></tr>
              <tr *ngFor="let riga of mat; let i = index">
                <td class="ch">{{ i }}</td>
                <td *ngFor="let v of riga; let j = index"
                    [class.diag]="i === j" [class.zero]="v === 0"
                    [style.opacity]="v ? (0.25 + 0.75 * v / maxCella(mat)) : 1">{{ v || '' }}</td>
              </tr>
            </table>
            <div class="axis">righe = voto umano · colonne = voto del giudice</div>
          </div>
        </div>

        <ng-container *ngIf="accordo.tassonomia_errori?.totale_codificati">
          <h3>Tassonomia degli errori</h3>
          <p class="hint">Distribuzione degli stadi in cui la risposta si perde, codificati a mano.</p>
          <div class="bars">
            <div class="brow" *ngFor="let e of tassonomia()">
              <span class="blab">{{ e.label }}</span>
              <div class="btrack"><i [style.width.%]="e.pct"></i></div>
              <span class="bval">{{ e.n }} ({{ e.pct | number:'1.0-0' }}%)</span>
            </div>
          </div>
        </ng-container>
      </ng-container>

      <!-- ================= PER DOMANDA ================= -->
      <ng-container *ngIf="vista === 'domande' && coda && !caricando">
        <p class="hint">
          Dove si perde la risposta, domanda per domanda. Lo stadio è dedotto dai dati del run;
          quello codificato a mano in annotazione ha la precedenza.
        </p>
        <table class="tab compact">
          <thead>
            <tr><th>ID</th><th>Domanda</th><th>Cat.</th><th>rank cand.</th><th>rank ctx</th>
                <th>must</th><th>stadio</th><th>lat.</th></tr>
          </thead>
          <tbody>
            <tr *ngFor="let it of coda.items">
              <td class="mono">{{ it.question_id }}</td>
              <td class="qq">{{ it.question }}</td>
              <td><span class="chip sm">{{ it.category }}</span></td>
              <td>{{ it.rank_pre_rerank || '—' }}</td>
              <td [class.bad]="!it.rank_post_rerank">{{ it.rank_post_rerank || 'assente' }}</td>
              <td>{{ it.must_contain_pass === null ? '—' : (it.must_contain_pass ? '✓' : '✗') }}</td>
              <td><span class="stage" [attr.data-s]="stadioDi(it)">{{ etichettaStadio(stadioDi(it)) }}</span></td>
              <td class="mono">{{ it.latency_s }}s</td>
            </tr>
          </tbody>
        </table>
      </ng-container>
    </div>
  `,
  styles: [`
    .val { display: block; }
    .topbar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
    .topbar label { font-size: 12px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: .06em; }
    select, input[type=text] {
      padding: 7px 10px; border: 1px solid var(--border); border-radius: 6px;
      background: var(--bg-card); color: var(--text); font-size: 13px; font-family: inherit;
    }
    input[type=text] { flex: 1; min-width: 200px; }

    .tabs2 { display: flex; gap: 4px; margin-bottom: 18px; flex-wrap: wrap; }
    .t2 { padding: 6px 14px; border: 1px solid var(--border); background: var(--bg-card);
          color: var(--text-secondary); border-radius: 999px; cursor: pointer; font-size: 13px; }
    .t2.on { background: var(--primary); color: #fff; border-color: var(--primary); font-weight: 600; }
    .badge { margin-left: 6px; font-size: 11px; opacity: .85; }

    .loading { text-align: center; padding: 48px 0; }
    .spin { width: 28px; height: 28px; border: 3px solid var(--border); border-top-color: var(--primary);
            border-radius: 50%; animation: sp .8s linear infinite; margin: 0 auto; }
    @keyframes sp { to { transform: rotate(360deg); } }
    .err { padding: 14px 16px; border-radius: 8px; background: #fef2f2; color: #991b1b; font-size: 14px; }

    .warn { padding: 12px 16px; border-left: 3px solid #d97706; background: rgba(217,119,6,.08);
            border-radius: 4px; font-size: 13.5px; margin-bottom: 16px; }
    .stale {
      border: 1px solid var(--error, #dc2626);
      border-left: 4px solid var(--error, #dc2626);
      background: rgba(220,38,38,.06);
      border-radius: 8px; padding: 18px 20px; margin-bottom: 18px;
    }
    .stale-h { font-weight: 700; font-size: 15px; color: #b91c1c; margin-bottom: 8px; }
    .stale p { margin: 0 0 8px; font-size: 13.5px; line-height: 1.55; }
    .stale-w { color: var(--text-secondary); }
    .blind { padding: 10px 14px; border-radius: 6px; background: rgba(37,99,235,.08);
             font-size: 13px; color: var(--text-secondary); margin-bottom: 14px; }

    .meta { display: flex; flex-wrap: wrap; gap: 8px 22px; font-size: 13px;
            color: var(--text-secondary); margin-bottom: 22px; }

    h3 { font-size: 15px; font-weight: 600; margin: 26px 0 6px; }
    h4 { font-size: 13px; font-weight: 600; margin: 0 0 8px; }
    .hint { font-size: 12.5px; color: var(--text-secondary); margin: 0 0 12px; line-height: 1.5; max-width: 78ch; }

    .tooltip-wrap { position: relative; display: inline-flex; align-items: center;
                    margin-left: 4px; cursor: help; vertical-align: middle; }
    .tooltip-icon { display: inline-flex; align-items: center; justify-content: center;
                    width: 15px; height: 15px; border-radius: 50%; background: var(--border);
                    color: var(--text-secondary); font-size: 10px; font-weight: 700;
                    font-style: italic; font-family: serif; text-transform: none;
                    letter-spacing: normal; transition: background .15s, color .15s; }
    .tooltip-wrap:hover .tooltip-icon { background: var(--primary); color: #fff; }
    .tooltip-text { visibility: hidden; opacity: 0; position: absolute; z-index: 100;
                     background: #1e293b; color: #e2e8f0; font-size: 11px; font-weight: 400;
                     font-style: normal; text-transform: none; letter-spacing: normal;
                     padding: 8px 10px; border-radius: 8px; white-space: normal; width: 230px;
                     line-height: 1.4; box-shadow: 0 4px 12px rgba(0,0,0,.3); pointer-events: none;
                     transition: opacity .15s, visibility .15s; }
    .tooltip-wrap:hover .tooltip-text { visibility: visible; opacity: 1; }
    .table-tip .tooltip-text { top: calc(100% + 6px); left: 50%; transform: translateX(-50%); }
    .table-tip .tooltip-text::after { content: ''; position: absolute; bottom: 100%; left: 50%;
                                       transform: translateX(-50%); border: 6px solid transparent;
                                       border-bottom-color: #1e293b; }

    .tab { width: 100%; border-collapse: collapse; font-size: 13.5px; margin-bottom: 8px; }
    .tab th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
              color: var(--text-secondary); padding: 8px 10px; border-bottom: 1px solid var(--border); font-weight: 500; }
    .tab td { padding: 9px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
    .tab.compact td, .tab.compact th { padding: 6px 8px; font-size: 12.5px; }
    .tab .strong { font-weight: 600; }
    .qq { max-width: 320px; }
    .mono { font-family: ui-monospace, Menlo, monospace; font-size: 12px; }
    .dim { color: var(--text-secondary); font-weight: 400; }
    .sig { color: var(--primary); font-weight: 600; }
    .bad { color: #b91c1c; }
    .unvalidated td { opacity: .62; }
    .flag { display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 3px;
            background: rgba(217,119,6,.14); color: #b45309; font-size: 10.5px; }

    .progress { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; font-size: 13px; color: var(--text-secondary); }
    .bar { flex: 1; height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
    .bar i { display: block; height: 100%; background: var(--primary); }

    .card { border: 1px solid var(--border); border-radius: 10px; padding: 20px; background: var(--bg-card); }
    .navrow { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
    .navrow button { padding: 5px 12px; border: 1px solid var(--border); background: var(--bg-card);
                     border-radius: 6px; cursor: pointer; color: var(--text); }
    .navrow button:disabled { opacity: .35; cursor: default; }
    .qid { font-family: ui-monospace, monospace; font-size: 13px; font-weight: 600; }
    .q { font-size: 17px; font-weight: 600; line-height: 1.35; margin-bottom: 10px; }

    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
    .chip { font-size: 11px; padding: 2px 9px; border-radius: 999px; background: var(--border); color: var(--text-secondary); }
    .chip.sm { font-size: 10.5px; }
    .chip.good { background: rgba(22,163,74,.14); color: #15803d; }
    .chip.bad { background: rgba(220,38,38,.12); color: #b91c1c; }

    .pane { margin-bottom: 12px; }
    .pane-t { font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
              color: var(--text-secondary); margin-bottom: 4px; }
    .pane-b { font-size: 14px; line-height: 1.55; white-space: pre-wrap;
              background: var(--bg); border-radius: 6px; padding: 12px 14px; max-height: 260px; overflow-y: auto; }
    .pane-b.ref { border-left: 3px solid var(--primary); }
    .srcs { margin: 0; padding-left: 22px; font-size: 12px; font-family: ui-monospace, monospace;
            color: var(--text-secondary); line-height: 1.7; }
    .srcs li.hit { color: #15803d; font-weight: 600; }

    .scores { margin-top: 18px; border-top: 1px solid var(--border); padding-top: 16px;
              display: flex; flex-direction: column; gap: 12px; }
    .srow { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
    .slab { width: 190px; font-size: 13px; font-weight: 500; }
    .slab small { display: block; font-weight: 400; font-size: 11px; color: var(--text-secondary); }
    .sbtns { display: flex; gap: 5px; }
    .sbtns button { width: 36px; height: 34px; border: 1px solid var(--border); background: var(--bg-card);
                    border-radius: 6px; cursor: pointer; font-size: 13px; color: var(--text); }
    .sbtns button.sel { background: var(--primary); color: #fff; border-color: var(--primary); font-weight: 700; }
    .sbtns .clr { width: 30px; color: var(--text-secondary); }

    .actions { display: flex; align-items: center; gap: 10px; margin-top: 18px; }
    .btn { padding: 9px 18px; border: none; border-radius: 8px; background: var(--primary);
           color: #fff; font-weight: 600; cursor: pointer; font-size: 13.5px; }
    .btn:disabled { opacity: .5; }
    .btn-ghost { padding: 7px 14px; border: 1px solid var(--border); border-radius: 8px;
                 background: var(--bg-card); color: var(--text); cursor: pointer; font-size: 13px; text-decoration: none; }
    .saved { font-size: 12.5px; color: #15803d; }

    .verdict { display: flex; gap: 22px; align-items: flex-start; padding: 20px 22px;
               border-radius: 10px; background: var(--bg-card); border: 1px solid var(--border); margin-bottom: 20px; }
    .verdict.ok { border-left: 4px solid #16a34a; }
    .verdict.ko { border-left: 4px solid #dc2626; }
    .vnum { font-size: 34px; font-weight: 700; letter-spacing: -.02em; white-space: nowrap; }
    .vtxt p { margin: 6px 0 0; font-size: 13.5px; line-height: 1.5; }

    .matrici { display: flex; flex-wrap: wrap; gap: 26px; margin-top: 18px; }
    .mat { flex: 0 0 auto; }
    .cm { border-collapse: collapse; font-size: 11.5px; }
    .cm td { width: 30px; height: 26px; text-align: center; border: 1px solid var(--border);
             background: rgba(37,99,235,.55); color: #fff; }
    .cm td.zero { background: transparent; color: var(--text-secondary); }
    .cm td.diag { outline: 2px solid #16a34a; outline-offset: -2px; }
    .cm .ch { background: transparent; color: var(--text-secondary); font-weight: 600; border: none; }
    .cm .cnr { border: none; background: transparent; }
    .axis { font-size: 10.5px; color: var(--text-secondary); margin-top: 5px; }

    .bars { display: flex; flex-direction: column; gap: 7px; max-width: 620px; }
    .brow { display: grid; grid-template-columns: 230px 1fr 90px; gap: 10px; align-items: center; font-size: 12.5px; }
    .btrack { height: 16px; background: var(--border); border-radius: 3px; overflow: hidden; }
    .btrack i { display: block; height: 100%; background: var(--primary); }
    .bval { text-align: right; color: var(--text-secondary); }

    .stage { font-size: 11px; padding: 2px 8px; border-radius: 4px; background: var(--border); }
    .stage[data-s="ok"] { background: rgba(22,163,74,.15); color: #15803d; }
    .stage[data-s="retrieval_miss"], .stage[data-s="corpus_miss"] { background: rgba(220,38,38,.12); color: #b91c1c; }
    .stage[data-s="reranker_drop"] { background: rgba(217,119,6,.15); color: #b45309; }
    .stage[data-s="generation_miss"], .stage[data-s="hallucination"] { background: rgba(124,58,237,.13); color: #6d28d9; }
  `],
})
export class ValutazioneComponent implements OnInit {
  viste = [
    { id: 'risultati', label: 'Risultati' },
    { id: 'annota', label: 'Annotazione' },
    { id: 'accordo', label: 'Corrispondenza' },
    { id: 'domande', label: 'Per domanda' },
  ];
  vista = 'risultati';

  runs: EvaluationRunSummary[] = [];
  runIdSelezionato = '';
  latest: EvaluationLatest | null = null;
  coda: AnnotationQueue | null = null;
  accordo: AgreementReport | null = null;

  caricando = false;
  salvando = false;
  errore = '';
  messaggio = '';

  indice = 0;
  ignoraDisallineamento = false;
  voti: Record<string, number | null> = { faithfulness: null, answer_relevance: null, correctness: null };
  stadio: string | null = null;
  nota = '';

  metricheRetrieval = ['hit_at_3', 'hit_at_5', 'mrr', 'recall_at_5', 'ndcg_at_5'];
  metricheGiudice = ['faithfulness', 'answer_relevance', 'correctness'];

  private ETICHETTE: Record<string, string> = {
    faithfulness: 'Fedeltà',
    answer_relevance: 'Pertinenza',
    correctness: 'Correttezza',
  };
  private DESCRIZIONI: Record<string, string> = {
    faithfulness: 'è supportata dai documenti mostrati?',
    answer_relevance: 'risponde davvero alla domanda?',
    correctness: 'concorda con la risposta di riferimento?',
  };
  private ETICHETTE_RETRIEVAL: Record<string, string> = {
    hit_at_3: 'Hit@3', hit_at_5: 'Hit@5', mrr: 'MRR',
    recall_at_5: 'Recall@5', ndcg_at_5: 'nDCG@5',
  };
  private DESCRIZIONI_RETRIEVAL: Record<string, string> = {
    hit_at_3: 'Percentuale di domande in cui almeno una fonte corretta compare fra i primi 3 risultati.',
    hit_at_5: 'Percentuale di domande in cui almeno una fonte corretta compare fra i primi 5 risultati.',
    mrr: 'Mean Reciprocal Rank: media dell\'inverso del rango della prima fonte corretta (1 se al primo posto, 0 se assente).',
    recall_at_5: 'Quota delle fonti rilevanti attese che compaiono fra i primi 5 risultati.',
    ndcg_at_5: 'Discounted Cumulative Gain normalizzato: pesa le fonti rilevanti in base alla posizione in classifica.',
  };

  constructor(private rag: RagService) {}

  ngOnInit(): void {
    this.rag.getEvaluationRuns().subscribe({
      next: (r) => {
        this.runs = r.runs || [];
        this.runIdSelezionato = this.runs.length ? this.runs[0].run_id : '';
        this.caricaTutto();
      },
      error: () => this.caricaTutto(),
    });
  }

  caricaTutto(): void {
    this.caricando = true;
    this.errore = '';
    const id = this.runIdSelezionato || undefined;

    this.rag.getEvaluationLatest(id).subscribe({
      next: (d) => { this.latest = d; this.caricando = false; },
      error: (e) => { this.errore = e.message; this.caricando = false; },
    });
    this.rag.getAnnotationQueue(id, true).subscribe({
      next: (d) => { this.coda = d; this.indice = 0; this.caricaVoti(); },
      error: () => {},
    });
    this.rag.getAgreement(id).subscribe({
      next: (d) => (this.accordo = d),
      error: () => {},
    });
  }

  get corrente(): AnnotationItem | null {
    return this.coda?.items?.[this.indice] ?? null;
  }
  get stadiKeys(): string[] {
    return this.coda ? Object.keys(this.coda.stadi_errore) : [];
  }

  private caricaVoti(): void {
    const a = this.corrente?.annotazione;
    this.voti = {
      faithfulness: a?.faithfulness ?? null,
      answer_relevance: a?.answer_relevance ?? null,
      correctness: a?.correctness ?? null,
    };
    this.stadio = a?.error_stage ?? null;
    this.nota = a?.note ?? '';
    this.messaggio = '';
  }

  vai(d: number): void {
    if (!this.coda) return;
    const n = this.indice + d;
    if (n >= 0 && n < this.coda.items.length) { this.indice = n; this.caricaVoti(); }
  }

  prossimaNonAnnotata(): void {
    if (!this.coda) return;
    const i = this.coda.items.findIndex((x, k) => k > this.indice && !x.annotazione);
    const j = i >= 0 ? i : this.coda.items.findIndex((x) => !x.annotazione);
    if (j >= 0) { this.indice = j; this.caricaVoti(); }
  }

  salva(avanti: boolean): void {
    const it = this.corrente;
    if (!it || !this.coda) return;
    this.salvando = true;
    this.rag.saveAnnotation({
      run_id: this.coda.run_id,
      question_id: it.question_id,
      faithfulness: this.voti['faithfulness'],
      answer_relevance: this.voti['answer_relevance'],
      correctness: this.voti['correctness'],
      error_stage: this.stadio,
      note: this.nota || null,
    }).subscribe({
      next: (r) => {
        this.salvando = false;
        this.messaggio = 'salvata';
        it.annotazione = {
          faithfulness: this.voti['faithfulness'],
          answer_relevance: this.voti['answer_relevance'],
          correctness: this.voti['correctness'],
          error_stage: this.stadio,
          note: this.nota || null,
        };
        if (this.coda) this.coda.annotate = r.annotate;
        this.rag.getAgreement(this.coda?.run_id).subscribe({ next: (d) => (this.accordo = d), error: () => {} });
        if (avanti) this.vai(1);
      },
      error: (e) => { this.salvando = false; this.errore = e.message; },
    });
  }

  // --- helper di presentazione ---------------------------------------------

  etichetta(m: string): string { return this.ETICHETTE[m] || m; }
  descrizione(m: string): string { return this.DESCRIZIONI[m] || ''; }
  etichettaRetrieval(k: string): string { return this.ETICHETTE_RETRIEVAL[k] || k; }
  descrizioneRetrieval(k: string): string { return this.DESCRIZIONI_RETRIEVAL[k] || ''; }
  isPct(k: string): boolean { return k.startsWith('hit'); }
  abs(v: number | undefined | null): number { return Math.abs(v ?? 0); }

  /** Affidabilità della metrica secondo l'accordo giudice-umano reale (non un flag statico
   *  di run): null finché l'accordo non è calcolabile, altrimenti kappa >= 0.61. */
  metricaAffidabile(m: string): boolean | null {
    const kappa = this.acc(m)?.kappa_quadratico;
    if (kappa === null || kappa === undefined) return null;
    return kappa >= 0.61;
  }

  ci(stadio: 'retrieved' | 'context', k: string): MetricCI | null {
    return this.latest?.retrieval_stages?.[stadio]?.ci?.[k] ?? null;
  }
  ciGen(m: string): MetricCI | null {
    return (this.latest?.generation as any)?.['ci']?.[m] ?? null;
  }
  gen(k: string): number | null {
    const v = (this.latest?.generation as any)?.[k];
    return typeof v === 'number' ? v : null;
  }
  eff(k: string): any { return this.latest?.reranker_effect?.[k] ?? null; }
  acc(m: string) { return this.accordo?.metriche?.[m] ?? null; }

  fmtCI(c: MetricCI | null, pct: boolean): string {
    if (!c || c.mean === null) return '—';
    const f = (x: number | null) => (x === null ? '—' : pct ? (100 * x).toFixed(1) + '%' : x.toFixed(3));
    return `${f(c.mean)} [${f(c.ci_low)}, ${f(c.ci_high)}]`;
  }
  pct(v: number | null | undefined): string {
    return v === null || v === undefined ? '—' : (100 * v).toFixed(1) + '%';
  }
  maxCella(m: number[][]): number {
    return Math.max(1, ...m.map((r) => Math.max(...r)));
  }
  combacia(src: string, attese: string[]): boolean {
    const s = (src || '').toLowerCase();
    return (attese || []).some((f) => f && s.includes(f.toLowerCase()));
  }
  stadioDi(it: AnnotationItem): string {
    return it.annotazione?.error_stage || it.suggerimento_stadio || 'ok';
  }
  etichettaStadio(s: string): string {
    const map: Record<string, string> = {
      ok: 'ok', fallback: 'fallback', corpus_miss: 'assente dal corpus',
      retrieval_miss: 'non recuperata', reranker_drop: 'scartata dal reranker',
      generation_miss: 'ignorata dal generatore', hallucination: 'allucinazione',
    };
    return map[s] || s;
  }
  tassonomia(): { label: string; n: number; pct: number }[] {
    const t = this.accordo?.tassonomia_errori;
    if (!t || !t.totale_codificati) return [];
    return Object.entries(t.conteggi)
      .map(([k, n]) => ({ label: t.etichette[k] || k, n, pct: (100 * n) / t.totale_codificati }))
      .sort((a, b) => b.n - a.n);
  }
  csvUrl(): string { return this.rag.annotationsCsvUrl(this.runIdSelezionato || undefined); }
}
