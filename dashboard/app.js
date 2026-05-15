/**
 * Risk Engine v2.0 — Dashboard App
 * Polls /api/state every 200ms and updates the UI in real-time.
 */

const POLL_INTERVAL = 200;
const API_URL = '/api/state';

// ─── State ──────────────────────────────────────────────────────────────

let previousState = null;
let killSwitchWasTriggered = false;

// ─── DOM References ─────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);

// ─── Clock ──────────────────────────────────────────────────────────────

function updateClock() {
    const now = new Date();
    $('clock').textContent = now.toLocaleTimeString('en-US', { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();

// ─── Gauge Drawing ──────────────────────────────────────────────────────

function drawGauge(canvasId, value, maxValue, color, unit = '%') {
    const canvas = $(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    const cx = w / 2, cy = h - 10;
    const radius = Math.min(w, h) - 20;

    ctx.clearRect(0, 0, w, h);

    // Background arc
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 0.45, Math.PI, 0, false);
    ctx.lineWidth = 12;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
    ctx.lineCap = 'round';
    ctx.stroke();

    // Value arc
    const pct = Math.min(value / maxValue, 1);
    const endAngle = Math.PI + (Math.PI * pct);
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 0.45, Math.PI, endAngle, false);
    ctx.lineWidth = 12;
    ctx.strokeStyle = color;
    ctx.lineCap = 'round';
    ctx.stroke();

    // Value text
    ctx.fillStyle = '#f1f5f9';
    ctx.font = '600 18px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    ctx.fillText(`${value.toFixed(1)}${unit}`, cx, cy - 4);
}

// ─── Format Helpers ─────────────────────────────────────────────────────

function fmtMoney(val) {
    if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
    if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(2)}M`;
    if (Math.abs(val) >= 1e3) return `$${(val / 1e3).toFixed(1)}K`;
    return `$${val.toFixed(2)}`;
}

function fmtQty(val) {
    if (Math.abs(val) >= 1e6) return `${(val / 1e6).toFixed(1)}M`;
    if (Math.abs(val) >= 1e3) return `${(val / 1e3).toFixed(1)}K`;
    return val.toFixed(0);
}

function shortTime(ts) {
    if (!ts) return '--:--:--';
    try {
        const d = new Date(ts);
        return d.toLocaleTimeString('en-US', { hour12: false });
    } catch { return ts.slice(11, 19); }
}

// ─── Update UI ──────────────────────────────────────────────────────────

function updateDashboard(state) {
    if (!state || !state.portfolio) return;

    const p = state.portfolio;
    const r = state.regime;
    const ks = state.kill_switch;

    // Metrics
    $('navValue').textContent = fmtMoney(p.nav);
    const changePct = p.daily_pnl_pct || 0;
    const changeEl = $('navChange');
    changeEl.textContent = `${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%`;
    changeEl.className = `metric-change ${changePct >= 0 ? 'positive' : 'negative'}`;

    $('drawdownValue').textContent = `${p.drawdown_pct.toFixed(2)}%`;
    const ddLimit = r.limits ? r.limits.max_drawdown_pct : 15;
    $('drawdownLimit').textContent = `Limit: ${ddLimit}%`;

    // Color drawdown card based on proximity to limit
    const ddCard = $('drawdownCard');
    if (p.drawdown_pct > ddLimit * 0.8) {
        ddCard.style.borderColor = 'rgba(239, 68, 68, 0.5)';
    } else if (p.drawdown_pct > ddLimit * 0.5) {
        ddCard.style.borderColor = 'rgba(245, 158, 11, 0.3)';
    } else {
        ddCard.style.borderColor = '';
    }

    $('regimeValue').textContent = `${r.emoji} ${r.state}`;
    $('volValue').textContent = `Vol: ${r.vol}%`;

    // Color regime card
    const regimeCard = $('regimeCard');
    if (r.state === 'CRISIS') regimeCard.style.borderColor = 'rgba(239, 68, 68, 0.4)';
    else if (r.state === 'ELEVATED') regimeCard.style.borderColor = 'rgba(245, 158, 11, 0.3)';
    else regimeCard.style.borderColor = '';

    $('tradesValue').textContent = p.trade_count;
    const anomalyStr = state.anomaly.in_warmup
        ? `Anomaly: warmup (${state.anomaly.order_count})`
        : `Anomaly: active (${state.anomaly.order_count})`;
    $('anomalyInfo').textContent = anomalyStr;

    // Kill Switch
    const ksContainer = $('killSwitchContainer');
    const ksState = $('killSwitchState');
    const ksDetail = $('killSwitchDetail');
    const ksIcon = $('killSwitchIcon');

    if (ks.is_active) {
        ksContainer.classList.add('triggered');
        ksState.textContent = ks.state;
        ksDetail.textContent = ks.trigger_reason || 'System halted';
        ksIcon.textContent = '🚨';

        if (!killSwitchWasTriggered) {
            killSwitchWasTriggered = true;
            // Flash the entire page briefly
            document.body.style.boxShadow = 'inset 0 0 100px rgba(239, 68, 68, 0.3)';
            setTimeout(() => { document.body.style.boxShadow = ''; }, 1000);
        }
    } else {
        ksContainer.classList.remove('triggered');
        ksState.textContent = 'ARMED';
        ksDetail.textContent = 'All systems nominal';
        ksIcon.textContent = '🛡️';
        killSwitchWasTriggered = false;
    }

    // Gauges
    const ddColor = p.drawdown_pct > ddLimit * 0.8 ? '#ef4444'
                   : p.drawdown_pct > ddLimit * 0.5 ? '#f59e0b' : '#22c55e';
    drawGauge('drawdownGauge', p.drawdown_pct, ddLimit, ddColor);

    const lastZ = (state.order_log && state.order_log.length > 0)
        ? (state.order_log[state.order_log.length - 1].anomaly_z || 0)
        : 0;
    const zColor = lastZ > 4 ? '#ef4444' : lastZ > 2 ? '#f59e0b' : '#22c55e';
    drawGauge('anomalyGauge', lastZ, 10, zColor, 'σ');

    const volColor = r.vol > 30 ? '#ef4444' : r.vol > 15 ? '#f59e0b' : '#22c55e';
    drawGauge('volGauge', r.vol, 50, volColor);

    // Order table
    if (state.order_log) {
        const tbody = $('orderBody');
        const rows = state.order_log.slice(-30).reverse();
        $('orderCount').textContent = state.order_log.length;

        tbody.innerHTML = rows.map(o => {
            const cls = o.action === 'KILL' ? 'kill'
                      : o.action === 'REJECT' ? 'reject' : 'pass';
            const fatClass = o.is_fat_finger ? ' fat-finger' : '';
            return `<tr class="${cls}${fatClass}">
                <td>${shortTime(o.timestamp)}</td>
                <td>${o.order_id}</td>
                <td class="side-${o.side.toLowerCase()}">${o.side}</td>
                <td>${fmtQty(o.quantity)}</td>
                <td>${fmtMoney(o.notional)}</td>
                <td>${(o.anomaly_z || 0).toFixed(1)}σ</td>
                <td>${o.action}</td>
            </tr>`;
        }).join('');
    }

    // Events
    if (state.events && state.events.length > 0) {
        const evtList = $('eventsList');
        evtList.innerHTML = state.events.slice().reverse().map(e => {
            const cls = e.severity === 'FATAL' ? 'event-fatal'
                      : e.severity === 'CRITICAL' ? 'event-critical'
                      : e.severity === 'WARN' ? 'event-warn' : 'event-info';
            return `<div class="event-item ${cls}">
                <span class="event-time">${shortTime(e.timestamp)}</span>
                <span class="event-msg">${e.message}</span>
            </div>`;
        }).join('');
    }
}

// ─── Polling ────────────────────────────────────────────────────────────

async function poll() {
    try {
        const res = await fetch(API_URL);
        if (res.ok) {
            const state = await res.json();
            updateDashboard(state);
            previousState = state;

            // Update connection status
            $('connectionStatus').innerHTML = '<span class="dot dot-green"></span><span>Connected</span>';
        }
    } catch (e) {
        $('connectionStatus').innerHTML = '<span class="dot dot-red"></span><span>Disconnected</span>';
    }
}

setInterval(poll, POLL_INTERVAL);
poll();
