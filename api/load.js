const { list } = require('@vercel/blob');

module.exports = async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const key = url.searchParams.get('key');
  if (!key) { res.status(400).send('Missing key'); return; }
  try {
    const { blobs } = await list({
      prefix: `reports/${key}.bin`,
      token: process.env.BLOB_READ_WRITE_TOKEN
    });
    if (!blobs.length) { res.status(404).send('Report not found'); return; }
    const response = await fetch(blobs[0].url);
    if (!response.ok) { res.status(404).send('Report not found'); return; }
    const data = await response.arrayBuffer();
    res.setHeader('Content-Type', 'application/octet-stream');
    res.setHeader('Cache-Control', 'public, max-age=604800');
    res.send(Buffer.from(data));
  } catch (e) {
    console.error('load error', e);
    res.status(500).send(e.message);
  }
};
