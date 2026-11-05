/**
 * n8n Code Node (JavaScript): Dynamic K-Medoids Clustering + Session Mini-Memory Saver
 * Author: Marcos Vinicius Beregula Ferreira (UEL - LABGEP / NIGEP)
 *
 * Usage:
 *   Place this node immediately after the PostgreSQL / Vector Search node in n8n.
 *   - If query returns <= 7 items: formats deterministic table directly and updates session lastTerm.
 *   - If query returns > 7 items: executes in-memory K-Medoids clustering (k=4),
 *     stores the full member lists per cluster in $getWorkflowStaticData('global').sessions[sessionId]
 *     (outside the SLM context window), and outputs the k representative medoid options.
 *   - Latency overhead: < 15ms on CPU. Zero external npm dependencies.
 */

// Helper to tokenize and build lexical word set
function extractTokens(item) {
  const text = `${item.codigo || ''} ${item.descricao || ''} ${item.titulo || ''} ${item.detalhe || ''}`.toLowerCase();
  const words = text.match(/[a-zà-ÿ0-9]{3,}/g) || [];
  return new Set(words);
}

// Jaccard distance between two token sets (1.0 = disjoint, 0.0 = identical)
function jaccardDistance(setA, setB) {
  if (setA.size === 0 && setB.size === 0) return 0.0;
  let intersection = 0;
  for (const item of setA) {
    if (setB.has(item)) intersection++;
  }
  const union = setA.size + setB.size - intersection;
  return union === 0 ? 0.0 : 1.0 - (intersection / union);
}

// Cosine distance for vector embeddings (when pgvector embedding column is present)
function cosineDistance(vecA, vecB) {
  let dot = 0.0, normA = 0.0, normB = 0.0;
  for (let i = 0; i < vecA.length; i++) {
    dot += vecA[i] * vecB[i];
    normA += vecA[i] * vecA[i];
    normB += vecB[i] * vecB[i];
  }
  const denominator = Math.sqrt(normA) * Math.sqrt(normB);
  return denominator === 0 ? 1.0 : 1.0 - (dot / denominator);
}

// Build a clean, non-redundant label for a medoid item (avoids repeating titulo when identical to descricao)
function buildMedoidLabel(item) {
  const codigo = String(item.codigo || '-').trim();
  const desc = String(item.descricao || '-').trim();
  const tit = String(item.titulo || '').trim();
  const normDesc = desc.toLowerCase().replace(/[\s\-–—]+/g, ' ');
  const normTit = tit.toLowerCase().replace(/[\s\-–—]+/g, ' ');
  const extraTit = (tit && tit !== '-' && normTit !== normDesc && !normDesc.includes(normTit))
    ? ` (${tit})`
    : '';
  return `\`${codigo}\` — ${desc}${extraTit}`;
}

// Partitioning Around Medoids (PAM) Algorithm returning medoids AND full cluster member arrays
function runKMedoids(items, k = 4, maxIter = 25) {
  const n = items.length;
  if (n <= k) {
    return items.map((item, idx) => ({
      grupo: idx + 1,
      medoid: item,
      totalItensNoGrupo: 1,
      descricaoGrupo: buildMedoidLabel(item),
      membros: [item]
    }));
  }

  const hasEmbeddings = Array.isArray(items[0].embedding) && items[0].embedding.length > 0;
  const tokenSets = hasEmbeddings ? null : items.map(extractTokens);

  // Precompute pairwise distance matrix
  const distMatrix = Array.from({ length: n }, (_, i) =>
    Array.from({ length: n }, (_, j) => {
      if (i === j) return 0.0;
      if (hasEmbeddings) return cosineDistance(items[i].embedding, items[j].embedding);
      return jaccardDistance(tokenSets[i], tokenSets[j]);
    })
  );

  // Initialize medoids evenly spaced across dataset
  const step = Math.floor(n / k);
  let medoids = Array.from({ length: k }, (_, i) => Math.min(i * step, n - 1));

  let clusters = {};
  for (let iter = 0; iter < maxIter; iter++) {
    clusters = {};
    for (const m of medoids) clusters[m] = [];

    // Assignment phase: assign each item to closest medoid (each medoid anchors its own cluster)
    for (let i = 0; i < n; i++) {
      if (clusters[i] !== undefined) {
        clusters[i].push(i);
        continue;
      }
      let bestM = medoids[0];
      let bestDist = distMatrix[i][bestM];
      for (let mIdx = 1; mIdx < medoids.length; mIdx++) {
        const m = medoids[mIdx];
        if (distMatrix[i][m] < bestDist) {
          bestDist = distMatrix[i][m];
          bestM = m;
        }
      }
      clusters[bestM].push(i);
    }

    // Update phase: select new medoid minimizing sum of distances within cluster
    let changed = false;
    const newMedoids = [];
    for (const m of medoids) {
      const members = clusters[m];
      if (!members || members.length === 0) {
        newMedoids.push(m);
        continue;
      }
      let bestCand = m;
      let minTotalDist = Infinity;
      for (const cand of members) {
        let sumDist = 0;
        for (const other of members) sumDist += distMatrix[cand][other];
        if (sumDist < minTotalDist) {
          minTotalDist = sumDist;
          bestCand = cand;
        }
      }
      if (bestCand !== m) changed = true;
      newMedoids.push(bestCand);
    }
    medoids = newMedoids;
    if (!changed) break;
  }

  // Format output clusters with real medoid and full member array for session state memory
  const uniqueMedoids = [...new Set(medoids)];
  return uniqueMedoids.map((m, idx) => {
    const memberIndices = clusters[m] && clusters[m].length > 0 ? clusters[m] : [m];
    const memberItems = memberIndices.map(i => items[i]);
    return {
      grupo: idx + 1,
      medoid: items[m],
      totalItensNoGrupo: memberItems.length,
      descricaoGrupo: buildMedoidLabel(items[m]),
      membros: memberItems
    };
  });
}

// Helper to format small result sets directly with clean Markdown line breaks
function formatDirectResults(items) {
  if (items.length === 0) {
    return 'Não encontrei esta despesa no banco de dados. Tente descrever de outra forma, como o tipo do material ou serviço.';
  }
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
    `Encontrei **${items.length} registro(s)**:\n\n` +
    blocks.join('\n\n---\n\n') +
    `\n\n---\nAlgum corresponde ao que você precisa? Posso refinar a busca.`
  );
}

// ----------------------------------------------------
// n8n Entrypoint Execution + Session Memory Persistence
// ----------------------------------------------------
const rawItems = $input.all().map(item => item.json).filter(item => item && item.codigo);
const totalResults = rawItems.length;

// Retrieve session metadata from static data (mirrored in globalThis.__SLM_SESSIONS__ so manual Editor Chat works too)
const staticData = $getWorkflowStaticData('global');
if (!globalThis.__SLM_SESSIONS__) {
  globalThis.__SLM_SESSIONS__ = staticData.sessions || {};
}
staticData.sessions = globalThis.__SLM_SESSIONS__;

const firstInput = $input.first() ? $input.first().json : {};
let upstreamSessionId = '';
let upstreamTerm = '';
let upstreamTurnCount = 1;
try {
  if (typeof $ === 'function') {
    const routerNode = $('Session Mini-Memory Router');
    if (routerNode && routerNode.first() && routerNode.first().json) {
      upstreamSessionId = routerNode.first().json.sessionId || '';
      upstreamTurnCount = Number(routerNode.first().json.turn_count || 1);
    }
  }
} catch (_) {
  // Ignore if upstream node is named differently or in standalone test
}

const sessionId = String(firstInput.sessionId || upstreamSessionId || 'default-session').trim();
const searchedTerm = String(firstInput.termo_busca || firstInput.lastTerm || upstreamTerm || '').trim();

const currentSession = staticData.sessions[sessionId] || {
  sessionId,
  lastTerm: searchedTerm || null,
  turnCount: upstreamTurnCount,
  clusters: null,
  updatedAt: Date.now()
};

if (searchedTerm) {
  currentSession.lastTerm = searchedTerm;
}
currentSession.turnCount = upstreamTurnCount;
currentSession.updatedAt = Date.now();

if (totalResults <= 7) {
  // Pass-through: Few items, clear cluster state and return deterministic formatted table
  currentSession.clusters = null;
  staticData.sessions[sessionId] = currentSession;

  return [{
    json: {
      acao: 'exibicao_direta',
      sessionId,
      totalEncontrado: totalResults,
      itens: rawItems,
      save_last_term: currentSession.lastTerm || '',
      save_turn_count: currentSession.turnCount,
      save_clusters_json: 'null',
      output: formatDirectResults(rawItems)
    }
  }];
} else {
  // High count: cluster via K-Medoids (k=4 based on 1st local Silhouette peak) and save to Mini-Memory
  const k = 4;
  const clusterResults = runKMedoids(rawItems, k);

  // Save full cluster members inside n8n Session Mini-Memory (outside the SLM context window!)
  currentSession.clusters = clusterResults;
  staticData.sessions[sessionId] = currentSession;

  const formattedDisambiguationPrompt =
    `Sua busca retornou **${totalResults} resultados**. Para facilitar a localização sem sobrecarregar a tela, agrupei os itens nos **${k} temas mais representativos**:\n\n` +
    clusterResults.map(c => `${c.grupo}. **Opção ${c.grupo}** *(${c.totalItensNoGrupo} itens)*: ${c.descricaoGrupo}`).join('\n\n') +
    `\n\n---\nDigite o **número da opção (1 a ${k})** para listar os itens daquele grupo, ou envie um termo mais específico para refinar.`;

  return [{
    json: {
      acao: 'desambiguacao_kmedoids_salva_em_memoria',
      sessionId,
      totalEncontrado: totalResults,
      kClusters: k,
      gruposSugeridos: clusterResults.map(c => ({
        grupo: c.grupo,
        totalItensNoGrupo: c.totalItensNoGrupo,
        descricaoGrupo: c.descricaoGrupo,
        medoid: c.medoid
      })),
      save_last_term: currentSession.lastTerm || '',
      save_turn_count: currentSession.turnCount,
      save_clusters_json: JSON.stringify(clusterResults),
      output: formattedDisambiguationPrompt
    }
  }];
}
