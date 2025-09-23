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

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-fuel-gauge]').forEach((el) => initFuelGauge(el));
    document.querySelectorAll('[data-escalate-toggle]').forEach((el) => initEscalate(el));
  });
})();
