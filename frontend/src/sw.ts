import { flushQueue } from './utils/offlineQueue';

self.addEventListener('sync', (event: any) => {
  if (event.tag === 'report-sync') {
    event.waitUntil(flushQueue());
  }
});
