(() => {
  function initFuelGauge(gauge) {
    const slider = gauge.querySelector('[data-fuel-slider]');
    const field = gauge.parentElement?.querySelector('input[type="hidden"][name="fuel_level"]');
    const needle = gauge.querySelector('.gauge-needle');
    const output = gauge.parentElement?.querySelector('[data-fuel-value]');

    function update(value) {
      const clamped = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
      const angle = -90 + (clamped / 100) * 180;
      if (needle) {
        needle.style.transform = `rotate(${angle}deg)`;
      }
      if (field) {
        field.value = String(clamped);
      }
      if (output) {
        output.textContent = `${clamped}%`;
      }
    }

    const initial = parseInt(field?.value ?? slider?.value ?? '50', 10);
    update(Number.isNaN(initial) ? 50 : initial);

    if (slider) {
      slider.addEventListener('input', (event) => {
        const value = parseInt(event.target.value, 10);
        update(Number.isNaN(value) ? 0 : value);
      });
    }
  }

  function initEscalate(button) {
    const targetId = button.dataset.target;
    const input = targetId ? document.getElementById(targetId) : null;
    if (!input) {
      return;
    }

    function sync() {
      const active = input.value === '1';
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
      button.textContent = active ? 'Escalate to supervisors (ON)' : 'Escalate to supervisors';
    }

    button.addEventListener('click', () => {
      input.value = input.value === '1' ? '0' : '1';
      sync();
    });

    sync();
  }

  function initPhotoViewer() {
    const viewer = document.querySelector('[data-photo-viewer]');
    if (!viewer) {
      return;
    }
    const image = viewer.querySelector('[data-photo-image]');
    const closeControls = viewer.querySelectorAll('[data-photo-close]');
    const downloadLink = viewer.querySelector('[data-photo-download]');
    const body = document.body;
    let activeTrigger = null;

    function closeViewer() {
      if (viewer.hasAttribute('hidden')) {
        return;
      }
      viewer.setAttribute('hidden', '');
      viewer.setAttribute('aria-hidden', 'true');
      if (image) {
        image.src = '';
      }
      if (downloadLink) {
        downloadLink.href = '';
        downloadLink.setAttribute('hidden', '');
      }
      body.classList.remove('photo-viewer-open');
      if (activeTrigger) {
        activeTrigger.focus();
      }
      activeTrigger = null;
    }

    function openViewer(src, trigger) {
      if (!image) {
        return;
      }
      activeTrigger = trigger || null;
      image.src = src;
      viewer.removeAttribute('hidden');
      viewer.removeAttribute('aria-hidden');
      if (downloadLink) {
        downloadLink.href = src;
        const parts = src.split('/');
        const fileName = parts[parts.length - 1] || 'inspection-photo';
        downloadLink.setAttribute('download', fileName);
        downloadLink.removeAttribute('hidden');
      }
      body.classList.add('photo-viewer-open');
      viewer.focus();
    }

    closeControls.forEach((control) => {
      control.addEventListener('click', closeViewer);
    });

    viewer.addEventListener('click', (event) => {
      if (event.target === viewer) {
        closeViewer();
      }
    });

    viewer.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        closeViewer();
      }
    });

    document.querySelectorAll('[data-photo-src]').forEach((button) => {
      button.addEventListener('click', () => {
        const src = button.getAttribute('data-photo-src');
        if (src) {
          openViewer(src, button);
        }
      });
      button.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          const src = button.getAttribute('data-photo-src');
          if (src) {
            openViewer(src, button);
          }
        }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-fuel-gauge]').forEach((el) => initFuelGauge(el));
    document.querySelectorAll('[data-escalate-toggle]').forEach((el) => initEscalate(el));
    initPhotoViewer();
  });
})();
