/* global Chart */
(function(){
  const $ = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  function showToast(message){
    const el = $('#toast');
    if(!el) return;
    el.textContent = message;
    el.hidden = false;
    setTimeout(()=>{ el.hidden = true; }, 2500);
  }

  function initTabs(){
    const tabs = $$('.tab');
    const panels = $$('.tab-panel');
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        panels.forEach(p => p.classList.add('hidden'));
        tab.classList.add('active');
        const targetSel = tab.getAttribute('data-target');
        const panel = $(targetSel);
        if(panel){ panel.classList.remove('hidden'); }
      });
    });
  }

  function secondsPer500mFromSplit(splitStr){
    if(!splitStr) return NaN;
    if(!splitStr.includes(':')) return NaN;
    const [m, s] = splitStr.split(':');
    const minutes = parseInt(m, 10);
    const seconds = parseFloat(s);
    const total = minutes*60 + seconds;
    if(!isFinite(total) || total <= 0) return NaN;
    return total;
  }
  function splitFromSecondsPer500(totalSeconds){
    if(!isFinite(totalSeconds) || totalSeconds <= 0) return '';
    const m = Math.floor(totalSeconds/60);
    const s = totalSeconds - m*60;
    // Always render with one decimal for consistency (e.g., 2:00.0)
    return `${m}:${s.toFixed(1).padStart(4,'0')}`;
  }

  function initFormHelpers(){
    const dateInput = $('#date');
    if(dateInput && !dateInput.value){
      const today = new Date();
      const y = today.getFullYear();
      const m = String(today.getMonth()+1).padStart(2,'0');
      const d = String(today.getDate()).padStart(2,'0');
      dateInput.value = `${y}-${m}-${d}`;
    }

    const distance = $('#distance_km');
    const duration = $('#duration_min');
    const split = $('#split');

    let isAutoUpdating = false;
    function withGuard(fn){
      if(isAutoUpdating) return;
      try{ isAutoUpdating = true; fn(); } finally { isAutoUpdating = false; }
    }

    function isFilledNumber(input){
      if(!input) return false;
      const v = parseFloat(input.value);
      return !isNaN(v) && v > 0;
    }
    function isFilledSplit(input){
      if(!input) return false;
      const s = secondsPer500mFromSplit(input.value);
      return !isNaN(s) && s > 0;
    }

    function recalcAll() {
      const haveDistance = isFilledNumber(distance);
      const haveDuration = isFilledNumber(duration);
      const haveSplit = isFilledSplit(split);

      // Case: distance + duration -> split
      if(haveDistance && haveDuration && !haveSplit){
        withGuard(() => {
          const dVal = parseFloat(distance.value);
          const durVal = parseFloat(duration.value);
          const hours = durVal / 60.0;
          const speedKmh = dVal / hours; // km/h
          const secPer500 = 1800.0 / speedKmh;
          split.value = splitFromSecondsPer500(secPer500);
        });
        return;
      }

      // Case: distance + split -> duration
      if(haveDistance && haveSplit && !haveDuration){
        withGuard(() => {
          const dVal = parseFloat(distance.value);
          const secPer500 = secondsPer500mFromSplit(split.value);
          const totalSeconds = secPer500 * (dVal * 2.0);
          duration.value = (totalSeconds/60.0).toFixed(0);
        });
        return;
      }

      // Case: duration + split -> distance
      if(haveDuration && haveSplit && !haveDistance){
        withGuard(() => {
          const durVal = parseFloat(duration.value);
          const secPer500 = secondsPer500mFromSplit(split.value);
          const distanceKm = (durVal * 60.0) / secPer500 * 0.5;
          distance.value = (Math.round(distanceKm * 100) / 100).toFixed(2);
        });
      }
    }

    if(distance && duration && split){
      distance.addEventListener('input', recalcAll);
      duration.addEventListener('input', recalcAll);
      split.addEventListener('input', recalcAll);
    }
  }

  function yearsAround(currentYear){
    const years = [];
    for(let y=currentYear-3; y<=currentYear+1; y++) years.push(y);
    return years;
  }

  async function fetchJSON(url){
    const res = await fetch(url);
    if(!res.ok) throw new Error('Network error');
    return await res.json();
  }

  function populateYearSelects(currentYear){
    const selects = ['#yearTableSelect', '#yearChartSelect'].map(sel => $(sel)).filter(Boolean);
    const ys = yearsAround(currentYear);
    for(const sel of selects){
      sel.innerHTML = '';
      ys.forEach(y => {
        const opt = document.createElement('option');
        opt.value = String(y);
        opt.textContent = String(y);
        if(y === currentYear) opt.selected = true;
        sel.appendChild(opt);
      });
    }
  }

  function formatKm(x){
    return (Math.round(x*100)/100).toFixed(2);
  }

  async function loadYearlyTable(){
    const sel = $('#yearTableSelect');
    const year = parseInt(sel.value, 10);
    const data = await fetchJSON(`/api/yearly_table?year=${year}`);
    const tbody = $('#yearlyTable tbody');
    const totalEl = $('#yearlyTotal');
    tbody.innerHTML = '';
    let total = 0;
    Object.entries(data.daily_mileage).forEach(([d, km]) => {
      const tr = document.createElement('tr');
      const td1 = document.createElement('td');
      const td2 = document.createElement('td');
      td1.textContent = d;
      td2.textContent = formatKm(km);
      tr.appendChild(td1); tr.appendChild(td2);
      tbody.appendChild(tr);
      total += km;
    });
    totalEl.textContent = formatKm(total);
  }

  let charts = {};

  function destroyChart(id){
    if(charts[id]){ charts[id].destroy(); delete charts[id]; }
  }

  function colorPalette(){
    return {
      purple: '#7c5cff',
      teal: '#00d1b2',
      red: '#ff6b6b',
      yellow: '#ffdd57',
      blue: '#4da3ff',
      pink: '#ff89d6',
      accent: '#00d1b2',
      muted: '#b7c0ff'
    };
  }

  async function loadCharts(){
    const sel = $('#yearChartSelect');
    const year = parseInt(sel.value, 10);
    const [tableData, monthlyData, allData] = await Promise.all([
      fetchJSON(`/api/yearly_table?year=${year}`),
      fetchJSON(`/api/monthly_totals?year=${year}`),
      fetchJSON('/api/data')
    ]);

    const colors = colorPalette();

    // Daily mileage line
    const dailyLabels = Object.keys(tableData.daily_mileage);
    const dailyValues = Object.values(tableData.daily_mileage);
    destroyChart('dailyLineChart');
    charts.dailyLineChart = new Chart($('#dailyLineChart'), {
      type: 'line',
      data: {
        labels: dailyLabels,
        datasets: [{
          label: 'km', data: dailyValues, borderColor: colors.purple, backgroundColor: 'rgba(124,92,255,0.25)', tension: 0.25, pointRadius: 0
        }]
      },
      options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } }
    });

    // Monthly totals by type (stacked)
    const months = Array.from({length:12}, (_,i)=>String(i+1).padStart(2,'0'));
    const typeList = monthlyData.session_types;
    const typeColors = [colors.teal, colors.red, colors.blue, colors.pink, colors.yellow];
    const datasets = typeList.map((t, i) => ({
      label: t,
      data: months.map(m => monthlyData.totals[m][t] || 0),
      backgroundColor: typeColors[i % typeColors.length]
    }));
    destroyChart('monthlyTotalsChart');
    charts.monthlyTotalsChart = new Chart($('#monthlyTotalsChart'), {
      type: 'bar',
      data: { labels: months, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } }
      }
    });

    // Speed scatter over time (all data; highlight selected year)
    const allPoints = (allData.rows || []).map(r => ({
      x: r.date, y: parseFloat(r.speed_kmh || 'NaN'), inYear: (new Date(r.date)).getFullYear() === year
    })).filter(p => !isNaN(p.y));
    destroyChart('speedScatterChart');
    charts.speedScatterChart = new Chart($('#speedScatterChart'), {
      type: 'scatter',
      data: {
        datasets: [
          { label: `Speed ${year} (km/h)`, data: allPoints.filter(p => p.inYear), borderColor: colors.accent, backgroundColor: 'rgba(0,209,178,0.6)' },
          { label: 'Other years (km/h)', data: allPoints.filter(p => !p.inYear), borderColor: colors.muted, backgroundColor: 'rgba(183,192,255,0.3)' }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        parsing: false,
        scales: { y: { beginAtZero: true, title: { display: true, text: 'km/h' } } }
      }
    });

    // Cumulative mileage line
    const cumLabels = tableData.cumulative.map(p => p.date);
    const cumValues = tableData.cumulative.map(p => p.km);
    destroyChart('cumulativeChart');
    charts.cumulativeChart = new Chart($('#cumulativeChart'), {
      type: 'line',
      data: { labels: cumLabels, datasets: [{ label: 'km', data: cumValues, borderColor: colors.teal, backgroundColor: 'rgba(0,209,178,0.25)', tension: 0.15, pointRadius: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } }
    });
  }

  function initSavedToast(){
    const params = new URLSearchParams(window.location.search);
    if(params.get('saved') === '1'){ showToast('Session saved'); }
  }

  function init(){
    initTabs();
    initFormHelpers();
    initSavedToast();

    const currentYear = new Date().getFullYear();
    populateYearSelects(currentYear);

    // listeners
    const tableYear = $('#yearTableSelect');
    const chartYear = $('#yearChartSelect');
    if(tableYear){ tableYear.addEventListener('change', loadYearlyTable); }
    if(chartYear){ chartYear.addEventListener('change', loadCharts); }

    loadYearlyTable().catch(console.error);
    loadCharts().catch(console.error);
  }

  document.addEventListener('DOMContentLoaded', init);
})();