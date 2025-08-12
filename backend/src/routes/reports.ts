import express from 'express';
import { generateThumbnail } from '../utils/thumbnail';

const router = express.Router();

router.post('/reports', async (req, res) => {
  const report = req.body;
  if (Array.isArray(report.media)) {
    for (const m of report.media) {
      if (m.buffer && m.type) {
        await generateThumbnail(Buffer.from(m.buffer, 'base64'), m.type);
      }
    }
  }
  res.status(201).json({ ok: true });
});

export default router;
