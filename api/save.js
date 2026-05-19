const { put } = require('@vercel/blob');

const MAX_BYTES = 4 * 1024 * 1024; // 4 MB safety limit

module.exports = async (req, res) => {
  if (req.method !== 'POST') { res.status(405).end(); return; }
  try {
    const chunks = [];
    let total = 0;
    for await (const chunk of req) {
      const buf = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      total += buf.length;
      if (total > MAX_BYTES) {
        res.status(413).json({ error: 'too large', limit: MAX_BYTES });
        return;
      }
      chunks.push(buf);
    }
    const rawBody = Buffer.concat(chunks).toString('utf8').trim();
    const buf = Buffer.from(rawBody, 'base64');
    const key = Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
    await put(`reports/${key}.bin`, buf, {
      access: 'public',
      addRandomSuffix: false,
      token: process.env.BLOB_READ_WRITE_TOKEN
    });
    res.status(200).json({ key });
  } catch (e) {
    console.error('save error', e);
    res.status(500).send(e.message);
  }
};
