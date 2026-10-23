const number = new Intl.NumberFormat('en-US');
let oauthConfigured = false;
let chartDays = [];
const fmtDate = (iso, options) => new Date(`${iso}T12:00:00`).toLocaleDateString('en-US', options);

function metric(id, value, format = x => number.format(x)) {
  document.getElementById(id).textContent = value == null ? '—' : format(value);
}

function render(data) {
  const days = data.days;
  chartDays = days;
  const today = days.at(-1);
  const live = data.source === 'google_health';
  const hasSleep = days.some(day => day.sleep_minutes != null);
  document.getElementById('source-label').textContent = live ? 'Google Health' : 'Demo data';
  document.getElementById('status-message').textContent = live
    ? `Connected to Google Health · Checked ${new Date(data.last_synced).toLocaleString('en-US')}.${hasSleep ? '' : ` No sleep measurements returned for these ${days.length} days.`}`
    : oauthConfigured ? "You're viewing sample health data. Connect Google Health to see your data." : 'Sample data is shown. Add a local .env to enable connection.';
  document.getElementById('date-label').textContent = fmtDate(today.date,{weekday:'long',month:'long',day:'numeric',year:'numeric'});
  metric('steps-value', today.steps);
  metric('heart-value', today.resting_heart_rate);
  metric('sleep-value', today.sleep_minutes, x => `${Math.floor(x/60)}h ${String(x%60).padStart(2,'0')}m`);
  document.getElementById('heart-note').textContent = live
    ? `Google Health daily resting estimate for ${fmtDate(today.date, {month:'short', day:'numeric'})}`
    : 'Daily resting heart rate';
  document.getElementById('sleep-note').textContent = hasSleep
    ? today.sleep_minutes == null ? 'No sleep measurement for this wake-up day' : 'Attributed to wake-up day'
    : `No sleep measurements in these ${days.length} days`;
  metric('calories-value', today.calories);
  document.getElementById('steps-progress').style.width = `${Math.min(100, (today.steps || 0)/10000*100)}%`;
  const average = key => {
    const values = days.map(d => d[key]).filter(x => x != null);
    return values.length ? Math.round(values.reduce((a,b) => a+b, 0)/values.length) : null;
  };
  document.getElementById('steps-average').innerHTML = `${average('steps') == null ? '—' : number.format(average('steps'))}<small> avg / day</small>`;
  document.getElementById('heart-average').innerHTML = `${average('resting_heart_rate') ?? '—'}<small> bpm avg</small>`;
  for (const name of ['steps', 'sleep', 'calories', 'heart']) {
    document.getElementById(`${name}-chart`).src = `/api/charts/${name}.svg?days=${days.length}`;
  }
}

const chartValues = {
  steps: day => day.steps == null ? 'No measurement' : `${number.format(day.steps)} steps`,
  sleep: day => day.sleep_minutes == null ? 'No measurement' : `${Math.floor(day.sleep_minutes/60)}h ${String(day.sleep_minutes%60).padStart(2,'0')}m asleep`,
  calories: day => day.calories == null ? 'No measurement' : `${number.format(day.calories)} kcal burned`,
  heart: day => day.resting_heart_rate == null ? 'No measurement' : `${number.format(day.resting_heart_rate)} bpm resting`,
};

document.querySelectorAll('.chart img').forEach(image => {
  const chart = image.parentElement;
  const name = image.id.replace('-chart', '');
  const tooltip = document.createElement('div');
  tooltip.className = 'chart-tooltip';
  tooltip.hidden = true;
  const guide = document.createElement('div');
  guide.className = 'chart-hover-guide';
  guide.hidden = true;
  chart.append(guide);
  chart.append(tooltip);
  chart.addEventListener('pointermove', event => {
    if (!chartDays.length) return;
    const bounds = chart.getBoundingClientRect();
    const fraction = (event.clientX - bounds.left) / bounds.width;
    const index = Math.max(0, Math.min(chartDays.length - 1, Math.floor((fraction - 0.055) / 0.93 * chartDays.length)));
    const day = chartDays[index];
    const center = (0.055 + 0.93 * (index + 0.5) / chartDays.length) * bounds.width;
    tooltip.textContent = `${fmtDate(day.date, {weekday:'short', month:'short', day:'numeric'})}\n${chartValues[name](day)}`;
    tooltip.style.left = `${Math.max(65, Math.min(bounds.width - 65, center))}px`;
    guide.style.left = `${center}px`;
    guide.hidden = false;
    tooltip.hidden = false;
  });
  chart.addEventListener('pointerleave', () => { tooltip.hidden = true; guide.hidden = true; });
});

async function load(days) {
  const response = await fetch(`/api/trends?days=${days}`);
  if (!response.ok) {
    const details = await response.json().catch(() => ({}));
    throw new Error(details.detail || `Could not load health data (${response.status})`);
  }
  render(await response.json());
}

async function loadStatus() {
  const response = await fetch('/api/status');
  const status = await response.json();
  oauthConfigured = status.configured;
  document.getElementById('connect-button').hidden = !status.configured || status.connected;
  document.getElementById('disconnect-button').hidden = !status.connected;
}

document.getElementById('disconnect-button').addEventListener('click', async () => {
  const response = await fetch('/auth/disconnect', {method:'POST'});
  if (response.ok) { await loadStatus(); await load(Number(document.querySelector('[data-days].selected').dataset.days)); }
});

document.querySelectorAll('[data-days]').forEach(button => button.addEventListener('click', async () => {
  document.querySelectorAll('[data-days]').forEach(b => {b.classList.toggle('selected', b === button); b.setAttribute('aria-pressed', String(b === button));});
  try { await load(Number(button.dataset.days)); }
  catch (error) { document.querySelector('.demo-banner span:last-child').textContent = error.message; }
}));
loadStatus().then(() => load(7)).catch(error => { document.getElementById('status-message').textContent = error.message; });
