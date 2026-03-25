/**
 * Site Map Crawler
 *
 * Gera um grafo DOT a partir das páginas internas de um site.
 */

const puppeteer = require('puppeteer');

const startUrlInput = process.argv[2];
const maxDepthArg = Number(process.argv[3]);
const maxDepth = Number.isInteger(maxDepthArg) ? maxDepthArg : 4;
const debug = process.argv.includes('--debug');

if (!startUrlInput) {
    console.error('Usage: node sitemap.js https://example.com [maxDepth] [--debug]');
    process.exit(1);
}

const startUrl = normalizeStartUrl(startUrlInput);
const allowedOrigin = startUrl.origin;

const pages = new Map();      // url -> { url, title, links }
const visited = new Set();    // urls already scraped
const nodeIds = new Map();    // url -> dot node id
let nodeCounter = 0;

function normalizeStartUrl(input) {
    const url = new URL(input);
    url.hash = '';
    return url;
}

function normalizeUrl(href, baseUrl, allowedOrigin) {
    if (typeof href !== 'string') return null;

    const raw = href.trim();
    if (!raw) return null;

    // Ignora links que não levam a navegação real
    if (
        raw.startsWith('#') ||
        /^javascript:/i.test(raw) ||
        /^mailto:/i.test(raw) ||
        /^tel:/i.test(raw) ||
        /^sms:/i.test(raw) ||
        /^data:/i.test(raw)
    ) {
        return null;
    }

    try {
        const url = new URL(raw, baseUrl);
        url.hash = '';

        // Mantém apenas páginas do mesmo origin
        if (url.origin !== allowedOrigin) return null;

        // Normalização leve de trailing slash
        if (url.pathname.length > 1 && url.pathname.endsWith('/')) {
            url.pathname = url.pathname.slice(0, -1);
        }

        return url.toString();
    } catch {
        return null;
    }
}

function getPageLabel(url) {
    try {
        const parsed = new URL(url);
        const path = parsed.pathname + parsed.search;
        return path === '' ? '/' : path;
    } catch {
        return url;
    }
}

function escapeDotLabel(text) {
    return String(text)
        .replace(/\\/g, '\\\\')
        .replace(/"/g, '\\"')
        .replace(/\n/g, '\\n');
}

function getNodeId(url) {
    if (!nodeIds.has(url)) {
        nodeIds.set(url, `n${++nodeCounter}`);
    }
    return nodeIds.get(url);
}

function ensurePage(url) {
    if (!pages.has(url)) {
        pages.set(url, { url, title: '', links: [] });
    }
}

async function scrapeSite(browser) {
    const queue = [{ url: startUrl.toString(), depth: 0 }];
    visited.add(startUrl.toString());
    ensurePage(startUrl.toString());

    while (queue.length > 0) {
        const { url, depth } = queue.shift();
        ensurePage(url);

        if (debug) {
            try {
                const parsed = new URL(url);
                console.error(`Scraping: ${parsed.toString()}`);
            } catch {
                console.error(`Scraping: ${url}`);
            }
        }

        const page = await browser.newPage();

        try {
            await page.goto(url, {
                waitUntil: 'domcontentloaded',
                timeout: 30000,
            });

            const title = await page.title().catch(() => '');
            const rawLinks = await page.$$eval(
                'a[href]:not([rel~="nofollow"])',
                elements => elements.map(el => el.getAttribute('href'))
            );

            const links = [...new Set(
                rawLinks
                    .map(href => normalizeUrl(href, url, allowedOrigin))
                    .filter(Boolean)
            )];

            pages.set(url, {
                url,
                title: title || '(sem título)',
                links,
            });

            if (depth < maxDepth) {
                for (const link of links) {
                    if (!visited.has(link)) {
                        visited.add(link);
                        ensurePage(link);
                        queue.push({ url: link, depth: depth + 1 });
                    }
                }
            }
        } catch (error) {
            pages.set(url, {
                url,
                title: '(falha ao carregar)',
                links: [],
            });

            if (debug) {
                console.error(`Failed on ${url}: ${error.message}`);
            }
        } finally {
            await page.close().catch(() => {});
        }
    }
}

(async () => {
    const browser = await puppeteer.launch({
        headless: 'new',
    });

    try {
        await scrapeSite(browser);

        console.log('digraph sitemap {');
        console.log('   overlap=false;');
        console.log('   bgcolor=transparent;');
        console.log('   splines=true;');
        console.log('   rankdir=TB;');
        console.log('   node [shape=Mrecord, fontname="Arial", fontsize=18, style=filled, fillcolor=deepskyblue];');

        for (const [url, pageData] of pages.entries()) {
            const nodeId = getNodeId(url);
            const label = `${escapeDotLabel(pageData.title || '(sem título)')}\\n${escapeDotLabel(getPageLabel(url))}`;
            console.log(`   ${nodeId} [label="${label}"];`);
        }

        for (const [fromUrl, pageData] of pages.entries()) {
            const fromNodeId = getNodeId(fromUrl);

            for (const toUrl of pageData.links) {
                if (!pages.has(toUrl)) continue;
                const toNodeId = getNodeId(toUrl);
                console.log(`   ${fromNodeId} -> ${toNodeId};`);
            }
        }

        console.log('}');
    } finally {
        await browser.close().catch(() => {});
    }
})();