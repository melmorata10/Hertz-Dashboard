// Proxy for SharePoint via Power Automate HTTP trigger.
// Accepts: POST { url: "https://prod-xx.westus.logic.azure.com/..." }
// Calls the Power Automate flow URL and streams the file back.

module.exports = async (req, res) => {
  if (req.method !== 'POST') { res.status(405).end(); return; }

  try {
    const chunks = [];
    for await (const chunk of req) chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    const { url } = JSON.parse(Buffer.concat(chunks).toString('utf8'));

    if (!url || !/^https:\/\//i.test(url)) {
      res.status(400).json({ error: 'Invalid or missing URL' });
      return;
    }

    // Only allow Microsoft / Power Automate domains
    const allowed = [
      'logic.azure.com',
      'make.powerautomate.com',
      'prod-',          // Power Automate regional prefixes
      'flow.microsoft.com',
      'sharepoint.com',
    ];
    const urlObj = new URL(url);
    const hostOk = allowed.some(d => urlObj.hostname.includes(d) || url.includes(d));
    if (!hostOk) {
      res.status(403).json({ error: 'Domain not allowed. Only Microsoft / Power Automate URLs are accepted.' });
      return;
    }

    const upstream = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });

    if (!upstream.ok) {
      const text = await upstream.text();
      res.status(upstream.status).json({ error: `Flow returned ${upstream.status}`, detail: text.slice(0, 300) });
      return;
    }

    const contentType = upstream.headers.get('content-type') || 'application/octet-stream';
    const data = Buffer.from(await upstream.arrayBuffer());

    res.setHeader('Content-Type', contentType);
    res.setHeader('Cache-Control', 'no-store');
    res.send(data);
  } catch (e) {
    console.error('sp-proxy error', e);
    res.status(500).json({ error: e.message });
  }
};
