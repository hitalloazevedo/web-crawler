/**
 * Site Map Crawler
 *
 * Markus Östberg
 * 2025-01-19
 */

const puppeteer = require('puppeteer');

let site = '';
let pages = {};
let visited = {};
let pageCounter = 0;
let debug = true;

// Set max depth of recursive pages to scrape
const maxDepth = 8;

// FIX #4: Limit total pages to avoid stack overflow / too many browser tabs
const maxPages = 800;

async function scrapePage(page, browser, depth) {
    if (depth >= maxDepth) {
        console.error("Reached maxDepth on page: " + page);
        return null;
    }

    // FIX #4: Guard against scraping too many pages
    if (pageCounter >= maxPages) {
        console.error("Reached maxPages limit on page: " + page);
        return null;
    }

    if (debug) {
        try {
            const url = new URL(page);
            console.error("Scraping page:");
            console.error(url.protocol);
            console.error(url.hostname);
            console.error(url.pathname);
            console.error(url.search);
            console.error(url.hash);
        } catch (error) {
            console.error("Failed to parse page url: " + page);
        }
    }

    const pageInstance = await browser.newPage();

    try {
        await pageInstance.goto(page);
    } catch (error) {
        console.error("Failed to load page: " + page);
        await pageInstance.close();
        return null;
    }

    pageCounter++;

    // Get link list
    let links = await pageInstance.evaluate(getLinks);

    // FIX #1: Pass `site` explicitly instead of relying on .map() parameters
    links = links.map(link => normalizeRelativeLink(link, site));

    // FIX #5: Filter out null values produced by normalizeRelativeLink
    links = links.filter(Boolean);

    // FIX #6: Strip hash fragments to avoid duplicate page scraping
    links = links.map(link => link.split('#')[0]).filter(Boolean);

    links = links.filter(filterNonUniqueLink);
    links = links.filter(filterExternal);   // FIX #2: now implemented below

    let title = await pageInstance.title();

    pages[page] = { url: page, title: title, links: links };

    links.filter(filterScrapedPages).forEach(function(link) {
        pages[link] = { url: link, title: '', links: [] };
    });

    links = links.filter(filterVisitedLinks);

    // Push unexplored pages to queue
    for (const link of links) {
        // Save page as visited before recursing to prevent re-entry
        visited[link] = true;

        await scrapePage(link, browser, depth + 1);
    }

    await pageInstance.close();
}

// Get all links not marked with nofollow
function getLinks() {
    const links = document.querySelectorAll('a:not([rel="nofollow"])');
    return Array.prototype.map.call(links, function(e) {
        return e.getAttribute('href');
    });
}

// Filter out non-unique links
function filterNonUniqueLink(link, index, self) {
    return self.indexOf(link) === index;
}

function filterVisitedLinks(link) {
    return typeof visited[link] === "undefined";
}

function filterScrapedPages(link) {
    return typeof pages[link] === "undefined";
}

// FIX #1: Corrected signature — baseUrl is now passed explicitly via arrow function in .map()
function normalizeRelativeLink(link, baseUrl) {
    if (!link || typeof link !== 'string') return null;

    // Skip non-navigable hrefs
    if (
        link.startsWith('mailto:') ||
        link.startsWith('tel:') ||
        link.startsWith('javascript:')
    ) {
        return null;
    }

    if (link.startsWith('/')) {
        return baseUrl + link;
    }

    return link;
}

// FIX #2: Implemented the missing filterExternal function
function filterExternal(link) {
    if (!link) return false;
    try {
        const url = new URL(link);
        const base = new URL(site);
        return url.hostname === base.hostname;
    } catch (e) {
        // If we can't parse it, discard the link
        return false;
    }
}

// Main Crawler script
(async () => {
    const browser = await puppeteer.launch();

    if (process.argv.length > 2) {
        site = process.argv[2];
    } else {
        console.log("You need to provide a site url to crawl. E.g: https://ostberg.dev/");
        await browser.close();
        process.exit();
    }

    console.log("digraph sitemap {");
    console.log("   overlap=false;");
    console.log("   bgcolor=transparent;");
    console.log("   splines=true;");
    console.log("   rankdir=TB;");
    console.log("   node [shape=Mrecord, fontname=\"Arial\", fontsize=18, style=filled, fillcolor=deepskyblue];");

    // Save home page as visited
    visited[site] = true;

    // FIX #3: Declare `depth` with const instead of implicit global
    const depth = 0;

    // Start scraping the site
    await scrapePage(site, browser, depth);

    // Create dot file nodes and edges
    Object.keys(pages).forEach(function(key) {
        const nodeName = key.replace(/\W/g, '');
        if (nodeName) {
            console.log("   " + nodeName + ' [label = "' + pages[key].title.replace(/"/g, '\\"') + '\\n' + pages[key].url.replace(site, '/') + '"];');
        }
    });

    Object.keys(pages).forEach(function(key) {
        pages[key].links.forEach(function(link) {
            const fromNodeName = key.replace(/\W/g, '');
            const toNodeName = link.replace(/\W/g, '');

            if (fromNodeName && toNodeName) {
                console.log("   " + fromNodeName + ' -> ' + toNodeName);
            }
        });
    });

    console.log("}");
    await browser.close();
    process.exit();
})();