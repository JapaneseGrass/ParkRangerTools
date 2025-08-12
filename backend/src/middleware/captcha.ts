import fetch from 'node-fetch';
import { Request, Response, NextFunction } from 'express';

export async function verifyCaptcha(req: Request, res: Response, next: NextFunction) {
  const token = req.body['cf-turnstile-response'] || req.body['h-captcha-response'];
  if (!token) {
    return res.status(400).json({ error: 'captcha required' });
  }
  const secret = process.env.TURNSTILE_SECRET || process.env.HCAPTCHA_SECRET;
  const verifyUrl = process.env.TURNSTILE_SECRET
    ? 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
    : 'https://hcaptcha.com/siteverify';
  const params = new URLSearchParams();
  params.append('secret', secret || '');
  params.append('response', token);
  params.append('remoteip', req.ip);
  const result = await fetch(verifyUrl, { method: 'POST', body: params });
  const data = await result.json();
  if (!data.success) {
    return res.status(400).json({ error: 'captcha failed' });
  }
  next();
}
