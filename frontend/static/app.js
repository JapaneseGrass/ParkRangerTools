(() => {
  function initFuelGauge(gauge) {
    const fieldContainer = gauge.closest('.fuel-field');
    const field = fieldContainer?.querySelector('input[type="hidden"][name="fuel_level"]');
    const needle = gauge.querySelector('[data-fuel-needle]');
    const dial = gauge.querySelector('[data-fuel-dial]');
    const output = fieldContainer?.querySelector('[data-fuel-value]');
    if (!dial || !needle) {
      return;
    }

    let currentValue = 50;

    function clamp(value) {
      if (!Number.isFinite(value)) {
        return 0;
      }
      return Math.max(0, Math.min(100, value));
    }

    function applyValue(value) {
      currentValue = clamp(Math.round(value));
      const angle = -90 + (currentValue / 100) * 180;
      needle.style.transform = `rotate(${angle}deg)`;
      dial.setAttribute('aria-valuenow', String(currentValue));
      dial.setAttribute('aria-valuetext', `${currentValue}% full`);
      if (field) {
        field.value = String(currentValue);
      }
      if (output) {
        output.textContent = `${currentValue}%`;
      }
    }

    function valueFromPoint(clientX, clientY) {
      const rect = dial.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height;
      const dx = clientX - centerX;
      let dy = centerY - clientY;
      if (dy <= 0) {
        dy = 0.0001;
      }
      let angle = (Math.atan2(dx, dy) * 180) / Math.PI;
      if (!Number.isFinite(angle)) {
        angle = 0;
      }
      const clampedAngle = Math.max(-90, Math.min(90, angle));
      const value = ((clampedAngle + 90) / 180) * 100;
      return clamp(value);
    }

    function handlePointer(event) {
      const value = valueFromPoint(event.clientX, event.clientY);
      applyValue(value);
    }

    let dragging = false;

    dial.addEventListener(
      'pointerdown',
      (event) => {
        event.preventDefault();
        dragging = true;
        dial.setPointerCapture(event.pointerId);
        dial.classList.add('is-dragging');
        handlePointer(event);
      },
      { passive: false }
    );

    dial.addEventListener(
      'pointermove',
      (event) => {
        if (!dragging) {
          return;
        }
        event.preventDefault();
        handlePointer(event);
      },
      { passive: false }
    );

    function endDrag(event) {
      if (!dragging) {
        return;
      }
      dragging = false;
      dial.classList.remove('is-dragging');
      if (dial.hasPointerCapture && dial.hasPointerCapture(event.pointerId)) {
        dial.releasePointerCapture(event.pointerId);
      }
    }

    dial.addEventListener('pointerup', endDrag);
    dial.addEventListener('pointercancel', endDrag);

    dial.addEventListener('keydown', (event) => {
      const { key } = event;
      let delta = 0;
      if (key === 'ArrowLeft' || key === 'ArrowDown') {
        delta = -5;
      } else if (key === 'ArrowRight' || key === 'ArrowUp') {
        delta = 5;
      } else if (key === 'PageDown') {
        delta = -10;
      } else if (key === 'PageUp') {
        delta = 10;
      } else if (key === 'Home') {
        event.preventDefault();
        applyValue(0);
        return;
      } else if (key === 'End') {
        event.preventDefault();
        applyValue(100);
        return;
      } else {
        return;
      }
      event.preventDefault();
      applyValue(currentValue + delta);
    });

    const initial = parseInt(field?.value ?? dial.getAttribute('aria-valuenow') ?? '50', 10);
    applyValue(Number.isNaN(initial) ? 50 : initial);
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
