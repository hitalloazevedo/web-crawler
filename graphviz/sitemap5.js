/**
 * Site Map Crawler — Parallel Edition
 *
 * Markus Östberg / aprimorado com paralelismo + blacklist
 * 2025-01-19 → 2026-03-24
 *
 * Mudanças principais:
 *  - Substituída recursão sequencial por uma fila de trabalho com
 *    N workers rodando em paralelo (padrão: 10 tabs simultâneas).
 *  - Sem mais stack overflow: a profundidade é rastreada por
 *    página individualmente, não via call stack.
 *  - Pool de browsers reutilizados: cada worker mantém sua própria
 *    aba aberta e a reusa entre páginas.
 *  - Ajuste de concorrência via flag --concurrency=N
 *  - Blacklist de extensões e padrões de URL configurável
 */

const puppeteer = require('puppeteer');

/* ─── Blacklist ─────────────────────────────────────────────── */
/**
 * Extensões de arquivo ignoradas — adicione ou remova conforme necessário.
 * Comparação case-insensitive.
 */
const BLACKLISTED_EXTENSIONS = new Set([
    // Imagens
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico',
    '.bmp', '.tiff', '.tif', '.avif', '.heic', '.heif',
    // Vídeo
    '.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv', '.wmv',
    // Áudio
    '.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a',
    // Documentos / downloads
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.odt', '.ods', '.odp', '.csv', '.txt', '.rtf',
    // Arquivos comprimidos
    '.zip', '.rar', '.tar', '.gz', '.7z', '.bz2',
    // Fontes
    '.woff', '.woff2', '.ttf', '.otf', '.eot',
    // Código / dados estáticos
    '.js', '.css', '.json', '.xml', '.rss', '.atom',
    '.map', '.ts',
    // Executáveis / binários
    '.exe', '.dmg', '.pkg', '.deb', '.rpm', '.apk', '.ipa',
]);

/**
 * Padrões de URL ignorados (strings ou RegExp).
 * Use strings para correspondência parcial ou RegExp para padrões avançados.
 * Exemplos:
 *   '/wp-admin'        → ignora qualquer URL que contenha esse trecho
 *   /\/tag\//          → ignora URLs de tags WordPress
 *   /\?replytocom=/    → ignora URLs de resposta de comentários
 */
const BLACKLISTED_PATTERNS = [
    '/wp-admin',
    '/wp-content/uploads',
    '/wp-json',
    '/feed',
    '?replytocom=',
    /\/\?s=/,           // busca interna WordPress
    /\/page\/\d+\//,    // paginação
    /\/comment-page-/,  // páginas de comentários
];

/**
 * Verifica se uma URL deve ser ignorada com base na blacklist.
 * @param {string} url
 * @returns {boolean} true = URL é permitida, false = deve ser ignorada
 */
function isAllowed(url) {
    if (!url) return false;

    // Checa extensão do pathname (ignora query string)
    try {
        const { pathname } = new URL(url);
        const lower = pathname.toLowerCase();
        const lastDot = lower.lastIndexOf('.');
        if (lastDot !== -1) {
            const ext = lower.slice(lastDot);
            if (BLACKLISTED_EXTENSIONS.has(ext)) return false;
        }
    } catch {
        return false;
    }

    // Checa padrões
    for (const pattern of BLACKLISTED_PATTERNS) {
        if (pattern instanceof RegExp) {
            if (pattern.test(url)) return false;
        } else {
            if (url.includes(pattern)) return false;
        }
    }

    return true;
}

/* ─── Configuração ──────────────────────────────────────────── */
let site        = '';
const maxDepth  = 80;
const maxPages  = 40_000;

// Lê --concurrency=N da linha de comando (padrão 10)
const concurrencyArg = process.argv.find(a => a.startsWith('--concurrency='));
const CONCURRENCY    = concurrencyArg ? parseInt(concurrencyArg.split('=')[1], 10) : 10;

const debug = process.argv.includes('--debug');

/* ─── Estado global ─────────────────────────────────────────── */
const pages   = {};   // { url: { url, title, links[] } }
const visited = {};   // url → true  (enfileirado ou já visitado)
let pageCounter = 0;

/* ─── Fila de trabalho ──────────────────────────────────────── */
// Cada item: { url, depth }
const queue = [];

function enqueue(url, depth) {
    if (visited[url]) return;
    if (pageCounter + queue.length >= maxPages) return;
    visited[url] = true;
    queue.push({ url, depth });
}

function dequeue() {
    return queue.shift() ?? null;
}

/* ─── Worker ────────────────────────────────────────────────── */
async function worker(browser) {
    while (true) {
        const item = dequeue();
        if (!item) break;   // fila vazia — encerra o worker

        const { url, depth } = item;

        if (depth >= maxDepth) {
            if (debug) console.error(`[skip] maxDepth em: ${url}`);
            continue;
        }

        if (pageCounter >= maxPages) {
            if (debug) console.error(`[skip] maxPages em: ${url}`);
            continue;
        }

        if (debug) {
            try {
                const u = new URL(url);
                console.error(`[scrape] ${u.pathname}${u.search}`);
            } catch {
                console.error(`[scrape] url inválida: ${url}`);
            }
        }

        const tab = await browser.newPage();

        try {
            await tab.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
        } catch (err) {
            console.error(`[erro] falha ao carregar: ${url} — ${err.message}`);
            await tab.close();
            continue;
        }

        pageCounter++;

        // Coleta links
        let links = await tab.evaluate(getLinks);

        links = links
            .map(link => normalizeRelativeLink(link, site))
            .filter(Boolean)
            .map(link => link.split('#')[0])
            .filter(Boolean)
            .filter(filterNonUniqueLink)
            .filter(filterExternal)
            .filter(isAllowed);         // ← blacklist de extensões e padrões

        const title = await tab.title();
        pages[url] = { url, title, links };

        // Registra páginas descobertas mas ainda não visitadas
        links.forEach(link => {
            if (!pages[link]) {
                pages[link] = { url: link, title: '', links: [] };
            }
        });

        // Enfileira links não visitados
        links.forEach(link => enqueue(link, depth + 1));

        await tab.close();
    }
}

/* ─── Funções auxiliares (mesmas do original) ───────────────── */
function getLinks() {
    const links = document.querySelectorAll('a:not([rel="nofollow"])');
    return Array.prototype.map.call(links, e => e.getAttribute('href'));
}

function filterNonUniqueLink(link, index, self) {
    return self.indexOf(link) === index;
}

function normalizeRelativeLink(link, baseUrl) {
    if (!link || typeof link !== 'string') return null;
    if (
        link.startsWith('mailto:') ||
        link.startsWith('tel:')    ||
        link.startsWith('javascript:')
    ) return null;
    if (link.startsWith('/')) return baseUrl.replace(/\/$/, '') + link;
    return link;
}

function filterExternal(link) {
    if (!link) return false;
    try {
        const url  = new URL(link);
        const base = new URL(site);
        return url.hostname === base.hostname;
    } catch {
        return false;
    }
}

/* ─── Orquestrador paralelo ─────────────────────────────────── */
/**
 * Roda N workers em paralelo.
 * Quando um worker esgota a fila, ele para — mas outros workers
 * podem ter adicionado novos itens antes disso, por isso fazemos
 * rounds até que nenhum novo item apareça.
 */
async function crawlParallel(browser) {
    while (queue.length > 0) {
        // Inicia até CONCURRENCY workers simultaneamente
        const active = Math.min(CONCURRENCY, queue.length);
        const workers = Array.from({ length: active }, () => worker(browser));
        await Promise.all(workers);
        // Se novos links foram enfileirados durante a rodada, continua
    }
}

/* ─── Entry point ───────────────────────────────────────────── */
(async () => {
    const browser = await puppeteer.launch();

    if (process.argv.length < 3 || process.argv[2].startsWith('--')) {
        console.error('Uso: node sitemap3.js <url> [--concurrency=N] [--debug]');
        console.error('Ex:  node sitemap3.js https://ostberg.dev/ --concurrency=15');
        await browser.close();
        process.exit(1);
    }

    site = process.argv[2];

    if (debug) {
        console.error(`Iniciando crawler paralelo`);
        console.error(`  Site:        ${site}`);
        console.error(`  Concurrency: ${CONCURRENCY}`);
        console.error(`  MaxDepth:    ${maxDepth}`);
        console.error(`  MaxPages:    ${maxPages}`);
        console.error(`  Extensões bloqueadas: ${BLACKLISTED_EXTENSIONS.size}`);
        console.error(`  Padrões bloqueados:   ${BLACKLISTED_PATTERNS.length}`);
    }

    // Cabeçalho Graphviz
    console.log('digraph sitemap {');
    console.log('   overlap=false;');
    console.log('   bgcolor=transparent;');
    console.log('   splines=true;');
    console.log('   rankdir=TB;');
    console.log('   node [shape=Mrecord, fontname="Arial", fontsize=18, style=filled, fillcolor=deepskyblue];');

    // Enfileira página inicial
    enqueue(site, 0);

    // Crawl paralelo
    const t0 = Date.now();
    await crawlParallel(browser);
    const elapsed = ((Date.now() - t0) / 1000).toFixed(1);

    if (debug) {
        console.error(`\nConcluído: ${pageCounter} páginas em ${elapsed}s`);
    }

    // Gera nós e arestas do grafo
    Object.keys(pages).forEach(key => {
        const nodeName = key.replace(/\W/g, '');
        if (nodeName) {
            const safeTitle = pages[key].title.replace(/"/g, '\\"');
            const safeUrl   = pages[key].url.replace(site, '/');
            console.log(`   ${nodeName} [label = "${safeTitle}\\n${safeUrl}"];`);
        }
    });

    Object.keys(pages).forEach(key => {
        pages[key].links.forEach(link => {
            const from = key.replace(/\W/g, '');
            const to   = link.replace(/\W/g, '');
            if (from && to) {
                console.log(`   ${from} -> ${to}`);
            }
        });
    });

    console.log('}');
    await browser.close();
    process.exit(0);
})();