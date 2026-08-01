import getDb from '../data/db.js';

export async function GET({ request, locals }) {
  const db = getDb(locals.runtime);
  // Query total count of permutations
  const countRow = await db.prepare('SELECT COUNT(*) as count FROM permutations').first();
  const totalRecords = countRow ? countRow.count : 0;
  
  const limitPerSitemap = 50000;
  const totalSitemaps = Math.ceil(totalRecords / limitPerSitemap);
  
  const urlObj = new URL(request.url);
  const host = urlObj.origin; // Dynamically gets the host (e.g. http://localhost:4321 or production domain)
  
  let sitemapsXml = '';
  for (let i = 1; i <= totalSitemaps; i++) {
    sitemapsXml += `  <sitemap>
    <loc>${host}/sitemap-${i}.xml</loc>
  </sitemap>\n`;
  }

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${sitemapsXml}</sitemapindex>`;

  return new Response(xml, {
    headers: {
      'Content-Type': 'application/xml',
      'Cache-Control': 'public, max-age=86400' // Cache for 1 day
    }
  });
}
