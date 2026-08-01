import { GET as getIndex } from './sitemap-index.xml.js';

export async function GET(context) {
  return getIndex(context);
}
