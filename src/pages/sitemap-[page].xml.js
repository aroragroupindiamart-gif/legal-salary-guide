import getDb from '../data/db.js';

export async function GET({ params, request, locals }) {
  const pageNum = parseInt(params.page || '1');
  const limit = 50000;
  const offset = (pageNum - 1) * limit;

  // Query slice from SQLite
  let records = [];
  const db = getDb(locals.runtime);
  try {
    const res = await db.prepare(`
      SELECT state, city, job_title 
      FROM permutations 
      LIMIT ? OFFSET ?
    `).bind(limit, offset).all();
    records = res.results || [];
  } catch (e) {
    console.error("Sitemap query error:", e);
  }

  if (records.length === 0) {
    return new Response('Sitemap page not found', { status: 404 });
  }

  const urlObj = new URL(request.url);
  const host = urlObj.origin;

  const urlsXml = records.map(r => 
    `  <url>
    <loc>${host}/${r.state}/${r.city}/${r.job_title}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>`
  ).join('\n');

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urlsXml}
</urlset>`;

  return new Response(xml, {
    headers: {
      'Content-Type': 'application/xml',
      'Cache-Control': 'public, max-age=86400' // Cache for 1 day
    }
  });
}
