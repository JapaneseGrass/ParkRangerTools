import React, { useEffect, useState } from 'react';
import { queueReport, flushQueue } from '../utils/offlineQueue';

interface Location {
  lat: number;
  lon: number;
}

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'video/mp4'];
const MAX_SIZE = 25 * 1024 * 1024; // 25MB
const MAX_VIDEO_DURATION = 20; // seconds

async function validateFiles(fileList: FileList): Promise<File[]> {
  const files: File[] = [];
  for (const file of Array.from(fileList)) {
    if (!ALLOWED_TYPES.includes(file.type) || file.size > MAX_SIZE) {
      throw new Error('Invalid file type or size');
    }
    if (file.type.startsWith('video/')) {
      const duration = await new Promise<number>((res, rej) => {
        const video = document.createElement('video');
        video.preload = 'metadata';
        video.onloadedmetadata = () => {
          res(video.duration);
        };
        video.onerror = () => rej(new Error('cannot load video'));
        video.src = URL.createObjectURL(file);
      });
      if (duration > MAX_VIDEO_DURATION) {
        throw new Error('Video too long');
      }
    }
    files.push(file);
  }
  return files;
}

const ReportForm: React.FC = () => {
  const [category, setCategory] = useState('');
  const [description, setDescription] = useState('');
  const [contact, setContact] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [location, setLocation] = useState<Location | null>(null);
  const [parkId, setParkId] = useState('');
  const [segmentId, setSegmentId] = useState('');
  const [showDisclaimer, setShowDisclaimer] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const p = params.get('parkId');
    const s = params.get('segmentId');
    if (p) setParkId(p);
    if (s) setSegmentId(s);
    navigator.geolocation.getCurrentPosition(pos => {
      setLocation({ lat: pos.coords.latitude, lon: pos.coords.longitude });
    });
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js');
    }
    flushQueue();
  }, []);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    try {
      const validated = await validateFiles(e.target.files);
      setFiles(validated);
    } catch (err) {
      alert((err as Error).message);
    }
  };

  const uploadMedia = async (file: File): Promise<string> => {
    const res = await fetch('/reports/presign', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: file.name, type: file.type })
    });
    const { url } = await res.json();
    await fetch(url, { method: 'PUT', body: file });
    return url.split('?')[0];
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const report = {
      parkId,
      segmentId,
      category,
      description,
      contact,
      location,
      media: [] as string[]
    };
    try {
      for (const f of files) {
        const url = await uploadMedia(f);
        report.media.push(url);
      }
      await fetch('/reports', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(report)
      });
    } catch (err) {
      await queueReport(report);
    }
    alert('Report submitted');
  };

  if (showDisclaimer) {
    return (
      <div className="modal">
        <p>Do not use this form for emergencies. Call <a href="tel:911">911</a>.</p>
        <button onClick={() => setShowDisclaimer(false)}>Continue</button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <input type="hidden" value={parkId} />
      <input type="hidden" value={segmentId} />
      <label>
        Category
        <select value={category} onChange={e => setCategory(e.target.value)} required>
          <option value="">Select</option>
          <option value="safety">Safety</option>
          <option value="maintenance">Maintenance</option>
        </select>
      </label>
      <label>
        Description
        <textarea value={description} onChange={e => setDescription(e.target.value)} required />
      </label>
      <label>
        Media
        <input type="file" multiple onChange={handleFileChange} />
      </label>
      <label>
        Contact Info
        <input value={contact} onChange={e => setContact(e.target.value)} />
      </label>
      <div>Location: {location ? `${location.lat.toFixed(3)}, ${location.lon.toFixed(3)}` : 'Loading...'}</div>
      <div className="cf-turnstile" data-sitekey="YOUR_TURNSTILE_SITE_KEY"></div>
      <button type="submit">Submit</button>
    </form>
  );
};

export default ReportForm;
