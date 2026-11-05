/**
 * n8n Code Node (JavaScript): Session Mini-Memory Router & Cluster Expansion Handler
 * Author: Marcos Vinicius Beregula Ferreira (UEL - LABGEP / NIGEP)
 *
 * Architecture Role (Pre-SLM Node):
 *   Replaces n8n's native LangChain 'Simple Memory' (Window Buffer Memory) to prevent:
 *     1. Context window overflow on CPU-bound SLMs (4,096 token limit).
 *     2. Cross-turn prompt contamination during tool calling.
 *     3. Redundant SLM/database calls when the user simply selects a K-Medoids cluster.
 *
 * Placement in n8n Workflow:
 *   [Webhook] ---> [Session Mini-Memory Router (THIS NODE)] ---> [IF: route_to_slm?]
 *                                                                   |-- true  --> [SLM Agent / Postgres]
 *                                                                   |-- false --> [Respond to Webhook]
 */

const SESSION_TTL_MS = 15 * 60 * 1000; // 15 minutes session expiration
const MAX_REFINEMENT_TURNS = 3;        // Auto-reset after 3 turns to avoid context contamination

// Initialize or retrieve global static memory store inside n8n V8 engine
// Note: n8n does not persist $getWorkflowStaticData('global') in 'manual' Editor Chat mode,
// so we mirror the session map in globalThis.__SLM_SESSIONS__ to support BOTH manual Chat UI and production Webhooks!
const staticData = $getWorkflowStaticData('global');
if (!globalThis.__SLM_SESSIONS__) {
  globalThis.__SLM_SESSIONS__ = staticData.sessions || {};
}
staticData.sessions = globalThis.__SLM_SESSIONS__;

const now = Date.now();

// Garbage collection: purge expired sessions to keep RAM footprint near zero
for (const [sid, sess] of Object.entries(staticData.sessions)) {
  if (!sess || (now - (sess.updatedAt || 0)) > SESSION_TTL_MS) {
    delete staticData.sessions[sid];
  }
}

// Extract incoming payload (from Load Session Memory Postgres node, Webhook, or Chat Trigger)
const inputItem = $input.first() ? $input.first().json : {};
const body = inputItem.body || inputItem;
const sessionId = String(inputItem.sessionId || body.sessionId || 'default-session').trim();
const rawMessage = String(inputItem.rawMessage || body.message || body.chatInput || inputItem.message || inputItem.chatInput || '').trim();
const normalizedMsg = rawMessage.toLowerCase();

// Retrieve session state from PostgreSQL slm_session_memory (if present) or fallback to staticData
let dbClusters = inputItem.db_clusters || null;
if (typeof dbClusters === 'string') {
  try { dbClusters = JSON.parse(dbClusters); } catch (_) { dbClusters = null; }
}

let session = (inputItem.db_last_term !== undefined || inputItem.db_clusters !== undefined)
  ? {
      sessionId,
      lastTerm: inputItem.db_last_term || null,
      turnCount: Number(inputItem.db_turn_count || 0),
      clusters: Array.isArray(dbClusters) ? dbClusters : null,
      updatedAt: now
    }
  : (staticData.sessions[sessionId] || {
      sessionId,
      lastTerm: null,
      turnCount: 0,
      clusters: null,
      updatedAt: now
    });

// Helper: Format budget items into a deterministic Markdown list without calling the SLM
function formatDeterministicTable(items, headerTitle) {
  const blocks = items.map((item, idx) => {
    const codigo = item.codigo || '-';
    const descricao = item.descricao || '-';
    const titulo = item.titulo && String(item.titulo).trim() ? String(item.titulo).trim() : '-';
    const detalhe = item.detalhe && String(item.detalhe).trim() ? String(item.detalhe).trim() : '-';
    return [
      `**${idx + 1}. Código: \`${codigo}\`**  `,
      `• **Descrição:** ${descricao}  `,
      `• **Título:** ${titulo}  `,
      `• **Detalhe:** ${detalhe}`
    ].join('\n');
  });

  return (
    `${headerTitle} (**${items.length} registros encontrados**):\n\n` +
    blocks.join('\n\n---\n\n') +
    `\n\n---\nAlgum corresponde ao que você precisa? Digite outra palavra-chave para nova busca.`
  );
}

// -----------------------------------------------------------------------------
// CASE 1: Explicit Context Reset Command
// -----------------------------------------------------------------------------
const resetPattern = /^(reiniciar|limpar|reset|nova busca|recomeçar|recomecar|cancelar|outro assunto)$/i;
if (resetPattern.test(normalizedMsg)) {
  delete staticData.sessions[sessionId];
  return [{
    json: {
      route_to_slm: false,
      acao_memoria: 'contexto_reiniciado',
      sessionId,
      save_last_term: '',
      save_turn_count: 0,
      save_clusters_json: 'null',
      output: 'Contexto da conversa reiniciado com sucesso. Digite a palavra-chave ou código da natureza de despesa que deseja pesquisar.'
    }
  }];
}

// -----------------------------------------------------------------------------
// CASE 2: User Selects a K-Medoids Cluster Option (e.g., "1", "opção 2", "grupo 3")
// -----------------------------------------------------------------------------
if (Array.isArray(session.clusters) && session.clusters.length > 0) {
  const choiceMatch = normalizedMsg.match(
    /^(?:op[cç][aã]o|grupo|item|topico|tópico|numero|número|quero o|quero a|ver o|ver a|abrir)?\s*([1-9])\b/i
  );

  if (choiceMatch) {
    const chosenGroupNum = parseInt(choiceMatch[1], 10);
    const chosenCluster = session.clusters.find(c => c.grupo === chosenGroupNum);

    if (chosenCluster && Array.isArray(chosenCluster.membros)) {
      const header = `Exibindo itens do **Grupo ${chosenCluster.grupo}** (${chosenCluster.descricaoGrupo})`;
      const responseText = formatDeterministicTable(chosenCluster.membros, header);

      // Keep clusters in session so the user can also inspect other options (e.g., "2" then "3")!
      session.turnCount += 1;
      session.updatedAt = now;
      staticData.sessions[sessionId] = session;

      return [{
        json: {
          route_to_slm: false,
          acao_memoria: 'expansao_cluster_direta',
          sessionId,
          grupoEscolhido: chosenGroupNum,
          totalItensGrupo: chosenCluster.membros.length,
          save_last_term: session.lastTerm || '',
          save_turn_count: session.turnCount,
          save_clusters_json: JSON.stringify(session.clusters),
          output: responseText
        }
      }];
    }
  }
}

// -----------------------------------------------------------------------------
// CASE 3: Incremental Refinement vs. Auto-Reset on Turn Limit / New Topic
// -----------------------------------------------------------------------------
const refinementPrefixPattern = /^(mas\s+|só\s+|so\s+|apenas\s+|somente\s+|especificamente\s+|para\s+|de\s+|do\s+|da\s+|tipo\s+|exceto\s+)/i;
const isShortRefinement = (
  session.lastTerm &&
  session.turnCount < MAX_REFINEMENT_TURNS &&
  (refinementPrefixPattern.test(normalizedMsg) || normalizedMsg.split(/\s+/).length <= 2) &&
  !/^(oi|olá|ola|bom dia|boa tarde|boa noite|ajuda|socorro)\b/i.test(normalizedMsg) &&
  !/^\d/.test(normalizedMsg)
);

let messageForSlm = rawMessage;
let memoryAction = 'nova_busca_limpa';

if (isShortRefinement && !normalizedMsg.includes(session.lastTerm.toLowerCase())) {
  // Lightweight context injection: combines previous search term with short modifier (~5 tokens total)
  const cleanModifier = rawMessage.replace(/^(?:(?:mas|só|so|apenas|somente|especificamente|para|de|do|da|tipo)\s+)+/i, '').trim();
  messageForSlm = `${session.lastTerm} ${cleanModifier}`.trim();
  session.turnCount += 1;
  memoryAction = 'refinamento_incremental';
} else {
  // Auto-reset session state to prevent cross-turn contamination in the SLM
  session = {
    sessionId,
    lastTerm: null,
    turnCount: 1,
    clusters: null,
    updatedAt: now
  };
  if (session.turnCount >= MAX_REFINEMENT_TURNS) {
    memoryAction = 'auto_reset_limite_turnos';
  }
}

session.updatedAt = now;
staticData.sessions[sessionId] = session;

return [{
  json: {
    route_to_slm: true,
    acao_memoria: memoryAction,
    sessionId,
    original_message: rawMessage,
    message: messageForSlm,
    turn_count: session.turnCount,
    save_last_term: session.lastTerm || '',
    save_turn_count: session.turnCount,
    save_clusters_json: 'null'
  }
}];
