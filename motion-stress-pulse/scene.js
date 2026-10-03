// The market stress dashboard as one shape that keeps changing what it is.
// Every number on screen is the real reading of 02.10.2026, taken from score.csv.
// 48 beats at 120 BPM: button, loader, ring, score, six month line, bands, breadth,
// the live market row, and the sentence the whole thing exists to qualify.
(() => {
  'use strict';

  // ---- the real data -------------------------------------------------------
  const CHANCE = [24.3, 22.0, 17.7, 14.8, 10.5, 12.4, 10.5, 13.6, 11.4, 10.5, 11.4, 15.8,
    11.9, 10.5, 10.5, 10.5, 16.9, 15.8, 11.8, 15.1, 15.9, 13.1, 10.9, 11.5, 12.7, 16.2,
    15.3, 15.5, 16.6, 10.5, 10.5, 10.5, 11.1, 14.4, 13.4, 13.9, 17.0, 17.5, 18.1, 20.9,
    17.2, 18.1, 19.0, 18.2];
  const S5FI = [65.3, 66.1, 62.3, 64.5, 59.9, 59.5, 69.5, 66.3, 62.9, 68.7, 64.9, 66.1,
    65.7, 70.7, 61.0, 55.0, 61.0, 59.4, 53.7, 46.7, 51.5, 43.5, 34.2, 39.2, 32.8, 29.2,
    31.4, 26.2, 25.1, 21.3];
  const BANDS = [[9.2, '0-44'], [16.5, '45-69'], [24.6, '70-84'], [31.0, '85+']];
  const BASE = 14.9, TODAY = 18.2, MSS = 60.1;

  const b = n => beat(n);
  const UI = { font: F.RUBIK, weight: 700, color: C.INK };
  const LBL = { font: F.RUBIK, weight: 500, color: C.INK2 };

  scene('main', 0, DUR, { bg: C.PAPER }, (root) => {
    const world = grp(root, W / 2, H / 2);     // camera
    const stack = grp(world, 0, 0);            // the shape and everything inside it

    // ---- the shape: one element that never gets cut -------------------------
    const shadow = box(stack, 0, 0, 10, 10, {
      background: 'rgba(90,72,38,0.18)', filter: 'blur(34px)',
    });
    const shape = box(stack, 0, 0, 10, 10, {
      background: C.WHITE, border: `2px solid ${C.LINE}`, overflow: 'hidden',
    });

    //                       w    h   radius
    const S = track([520, 150, 75], [
      [b(4), [150, 150, 75], 20, 0.86],        // loader
      [b(5.6), [640, 640, 320], 15, 0.86],     // ring
      [b(12.6), [880, 480, 48], 15, 0.86],     // score card
      [b(18.6), [1180, 560, 40], 14, 0.88],    // six month line
      [b(26.6), [1020, 620, 44], 15, 0.86],    // bands
      [b(32.6), [820, 560, 44], 15, 0.86],     // breadth
      [b(37.6), [900, 280, 140], 17, 0.86],    // the market row
      [b(42.4), [760, 300, 150], 20, 0.84],    // the toast
      [b(46.8), [520, 150, 75], 15, 0.88],     // back to the button
    ]);
    const FILL = track(0, [[b(5.6), 1], [b(12.6), 0], [b(42.4), 1], [b(46.8), 0]], 14, 1);

    // ---- camera: each state fills about two thirds of the frame -------------
    // growing: the camera pulls back a touch early; shrinking: it comes in late.
    const Z = track(1.80, [
      [b(3.9), 2.40, 9, 0.98],
      [b(5.5), 1.46, 8, 0.98],
      [b(12.5), 1.08, 8, 0.98],
      [b(18.5), 0.80, 8, 0.98],
      [b(26.7), 0.92, 8, 0.98],
      [b(32.7), 1.14, 8, 0.98],
      [b(37.7), 1.05, 8, 0.98],
      [b(42.3), 1.24, 8, 0.98],
      [b(46.9), 1.80, 8, 0.98],
    ]);

    // ---- content groups ------------------------------------------------------
    // the shape is positioned by its top left corner, so content hangs off a group
    // that seek() keeps at the shape's centre.
    const inner = grp(shape, 0, 0);
    const mk = () => grp(inner, 0, 0);

    // 1. the button
    const gBtn = mk();
    box(gBtn, 0, 0, 520, 150, { background: C.INK, borderRadius: '75px' });
    txt(gBtn, 'בדיקת סיכון', { ...UI, size: 46, color: C.PAPER, y: 0 });

    // 2. loader
    const gLoad = mk();
    const loadSvg = svgBox(gLoad, -60, -60, 120, 120);
    const loadArc = svgEl('circle', loadSvg, {
      cx: 60, cy: 60, r: 44, fill: 'none', stroke: C.ACC, 'stroke-width': 10,
      'stroke-linecap': 'round', 'stroke-dasharray': '70 206',
    });

    // 3. the ring
    const gRing = mk();
    const RR = 228, CIRC = 2 * Math.PI * RR;
    const ringSvg = svgBox(gRing, -278, -278, 556, 556);
    svgEl('circle', ringSvg, { cx: 278, cy: 278, r: RR, fill: 'none', stroke: C.LINE, 'stroke-width': 44 });
    const ringArc = svgEl('circle', ringSvg, {
      cx: 278, cy: 278, r: RR, fill: 'none', stroke: C.ACC, 'stroke-width': 44,
      'stroke-linecap': 'round', 'stroke-dasharray': `${CIRC} ${CIRC}`,
      'stroke-dashoffset': CIRC, transform: 'rotate(-90 278 278)',
    });
    const tickA = 2 * Math.PI * BASE / 40;    // the dial runs 0 to 40 per cent
    const ringTick = svgEl('line', ringSvg, {
      x1: 278 + 200 * Math.sin(tickA), y1: 278 - 200 * Math.cos(tickA),
      x2: 278 + 258 * Math.sin(tickA), y2: 278 - 258 * Math.cos(tickA),
      stroke: C.GREY, 'stroke-width': 7, 'stroke-linecap': 'round',
    });
    const ringNum = txt(gRing, '0.0%', { size: 124, font: F.D, weight: 900, color: C.INK, y: -30, dir: 'ltr' });
    const ringCap = txt(gRing, 'סיכוי לנפילה של 5%', { size: 33, ...LBL, y: 62 });
    const gWatch = grp(gRing, 0, 178);
    box(gWatch, 0, 0, 220, 64, { background: '#dfe8ea', borderRadius: '32px' });
    txt(gWatch, 'WATCH', { size: 32, ...UI, color: '#2f5560', dir: 'ltr' });

    // 4. the raw score
    const gScore = mk();
    txt(gScore, 'ציון גולמי', { size: 36, ...LBL, y: -150 });
    const scoreNum = txt(gScore, '0', { size: 144, font: F.D, weight: 900, color: C.INK, y: -46, dir: 'ltr' });
    txt(gScore, 'מתוך 100', { size: 30, ...LBL, y: 40 });
    box(gScore, 0, 106, 640, 18, { background: C.LINE, borderRadius: '9px' });
    const scoreBarWrap = grp(gScore, -320, 106);
    const scoreBar = rect(scoreBarWrap, 0, -9, 640, 18, { background: C.ACC, borderRadius: '9px', transformOrigin: '0 50%' });
    const gTrend = grp(gScore, 0, 170);
    txt(gTrend, 'עולה 5 ימים ‎+4.1', { size: 32, ...LBL });

    // 5. the six month line
    const gChart = mk();
    const CW = 1040, CH = 320;
    const chartSvg = svgBox(gChart, -CW / 2, -CH / 2 - 24, CW, CH);
    const lo = Math.min(...CHANCE), hi = Math.max(...CHANCE);
    // reading order: the oldest day on the right, today on the left
    const px = i => CW - i * CW / (CHANCE.length - 1);
    const py = v => CH - 26 - (v - lo) / (hi - lo) * (CH - 64);
    const pts = CHANCE.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(' ');
    const chartBase = svgEl('line', chartSvg, {
      x1: 0, y1: py(BASE), x2: CW, y2: py(BASE), stroke: C.GREY,
      'stroke-width': 3, 'stroke-dasharray': '10 10',
    });
    const chartLine = svgEl('polyline', chartSvg, {
      points: pts, fill: 'none', stroke: C.ACC, 'stroke-width': 7,
      'stroke-linejoin': 'round', 'stroke-linecap': 'round',
    });
    const CLEN = 2600;
    chartLine.setAttribute('stroke-dasharray', CLEN);
    const chartDot = svgEl('circle', chartSvg, { cx: px(CHANCE.length - 1), cy: py(TODAY), r: 13, fill: C.ACC });
    const gTip = grp(gChart, -CW / 2 + px(CHANCE.length - 1) + 110, -CH / 2 - 24 + py(TODAY) - 76);
    box(gTip, 0, 0, 260, 74, { background: C.INK, borderRadius: '16px' });
    txt(gTip, '02.10 · 18.2%', { size: 31, ...UI, color: C.PAPER, dir: 'ltr' });
    const chartCap = txt(gChart, 'חצי שנה אחורה, המקווקו הוא יום רגיל', { size: 30, ...LBL, y: CH / 2 + 10 });

    // 6. the four bands
    const gBands = mk();
    txt(gBands, 'מה קרה היסטורית בכל רמה', { size: 34, ...LBL, y: -252 });
    const barFill = [], barNum = [];
    BANDS.forEach(([rate, label], i) => {
      const bw = 190, gap = 46, x = (1.5 - i) * (bw + gap);   // the first band on the right
      const g = grp(gBands, x, 190);
      const h = rate * 8.6;
      barFill.push(rect(g, -bw / 2, -h, bw, h, {
        background: ['#aba593', '#8a8373', '#625c4e', '#3b3730'][i],
        borderRadius: '14px', transformOrigin: '50% 100%',
      }));
      barNum.push(txt(g, `${rate.toFixed(1)}%`, { size: 34, ...UI, y: -h - 36, dir: 'ltr' }));
      txt(g, label, { size: 28, ...LBL, y: 46, dir: 'ltr' });
    });
    const gHere = grp(gBands, (1.5 - 1) * 236, 190 - 16.5 * 8.6 - 108);
    box(gHere, 0, 0, 180, 56, { background: C.INK, borderRadius: '28px' });
    txt(gHere, 'היום כאן', { size: 30, ...UI, color: C.PAPER });

    // 7. market breadth
    const gBr = mk();
    txt(gBr, 'רוחב השוק', { size: 36, ...LBL, y: -196 });
    const brNum = txt(gBr, '0.0%', { size: 112, font: F.D, weight: 900, color: C.INK, y: -104, dir: 'ltr' });
    txt(gBr, 'מהמניות מעל ממוצע 50 הימים', { size: 30, ...LBL, y: -14 });
    const BW = 640, BH = 150;
    const brSvg = svgBox(gBr, -BW / 2, 26, BW, BH);
    const slo = Math.min(...S5FI), shi = Math.max(...S5FI);
    const sp_ = S5FI.map((v, i) => `${(BW - i * BW / (S5FI.length - 1)).toFixed(1)},${(BH - 14 - (v - slo) / (shi - slo) * (BH - 34)).toFixed(1)}`).join(' ');
    const brLine = svgEl('polyline', brSvg, {
      points: sp_, fill: 'none', stroke: C.ACC, 'stroke-width': 6,
      'stroke-linejoin': 'round', 'stroke-linecap': 'round', 'stroke-dasharray': 1400,
    });
    const brCap = txt(gBr, 'חמישה גורמי רוחב נכנסים לציון', { size: 30, ...LBL, y: 230 });

    // 8. the live market row
    const gMkt = mk();
    const mktA = txt(gMkt, 'VIX 15.45', { size: 46, ...UI, x: 196, y: -24, dir: 'ltr' });
    const mktB = txt(gMkt, 'פתיחה ‎+0.78%', { size: 46, ...UI, x: -176, y: -24 });
    const mktCap = txt(gMkt, 'מחירי המסחר, להקשר בלבד', { size: 29, ...LBL, y: 54 });

    // 9. the toast
    const gToast = mk();
    txt(gToast, 'לא הוראת פעולה', { size: 54, ...UI, y: -30 });
    txt(gToast, 'הערכת סיכון בלבד', { size: 30, ...LBL, y: 42 });

    // ---- cursor, above the world --------------------------------------------
    const cur = cursor(root, 58, C.INK, C.WHITE);
    const CUR = track([250, 150], [
      [b(1.2), [60, 40], 14, 0.95],
      [b(4.4), [430, -300], 10, 0.98],      // out of the way while the system works
      [b(16.6), [120, 150], 13, 0.92],      // to the history control
      [b(19.4), [440, -290], 10, 0.98],
      [b(23.4), [-320, -60], 12, 0.94],     // hovering the last point of the line
      [b(26.4), [440, -290], 10, 0.98],
      [b(39.4), [40, 30], 13, 0.92],        // the click that raises the toast
      [b(41), [-150, 150], 11, 0.95],      // drifts away while the toast rises
      [b(43.4), [250, 150], 10, 0.98],
    ]);
    const PRESS = track(1, [
      [b(3), 0.86, 38, 1], [b(3.2), 1, 38, 1],
      [b(17.4), 0.86, 38, 1], [b(17.6), 1, 38, 1],
      [b(40), 0.86, 38, 1], [b(40.2), 1, 38, 1],
    ]);
    const CUR_O = track(1, [[b(5.4), 0, 16, 1], [b(16), 1, 16, 1], [b(20), 0, 16, 1],
      [b(22.8), 1, 16, 1], [b(26.8), 0, 16, 1], [b(38.8), 1, 16, 1]], 16, 1);

    // ---- the numbers that count up ------------------------------------------
    const RING = track(0, [[b(7), TODAY, 11, 0.92], [b(46.8), 0, 14, 1]]);
    const TICK_O = track(0, [[b(9.4), 1, 18, 1], [b(12.6), 0, 20, 1]], 18, 1);
    const SCORE = track(0, [[b(14), MSS, 12, 0.92], [b(46.8), 0, 14, 1]]);
    const DRAW = track(0, [[b(20.4), 1, 7, 1], [b(26.8), 0, 14, 1]]);    // the line draws itself
    const BARS = track(0, [[b(27.4), 1, 16, 0.84], [b(32.6), 0, 20, 1]]);
    const BRDRAW = track(0, [[b(33.6), 1, 8, 1], [b(37.6), 0, 14, 1]]);
    const BRNUM = track(0, [[b(33.4), 23.1, 12, 0.92], [b(37.6), 0, 14, 1]]);

    // ---- sound, on the beats where something lands ---------------------------
    sfx(b(3), 'click'); sfx(b(5.6), 'whoosh', 0.5); sfx(b(7), 'pop', 0.9);
    sfx(b(9.4), 'tick', 0.6); sfx(b(11), 'tick', 0.7); sfx(b(14), 'tick', 0.6);
    sfx(b(16), 'tick', 0.5); sfx(b(17.4), 'click'); sfx(b(20.4), 'swish', 0.5);
    sfx(b(24), 'tick', 0.5); sfx(b(27.4), 'hit', 0.7); sfx(b(29), 'tick', 0.7);
    sfx(b(33.4), 'swish', 0.45); sfx(b(35.4), 'tick', 0.6); sfx(b(38.4), 'tick', 0.5);
    sfx(b(40), 'click'); sfx(b(42.4), 'pop', 0.9);

    report('states', 9);

    return t => {
      // the shape
      const [w, h, r] = S(t);
      const f = FILL(t);
      const mix = (a, bb, k) => Math.round(lerp(a, bb, k));
      shape.style.background = `rgb(${mix(255, 251, f)},${mix(255, 247, f)},${mix(255, 238, f)})`;
      [shape, shadow].forEach((el, i) => {
        el.style.width = w.toFixed(1) + 'px';
        el.style.height = h.toFixed(1) + 'px';
        el.style.left = (-w / 2).toFixed(1) + 'px';
        el.style.top = (-h / 2 + (i === 0 ? 16 : 0)).toFixed(1) + 'px';
        el.style.borderRadius = r.toFixed(1) + 'px';
      });

      tf(inner, { x: w / 2, y: h / 2 });

      // camera: the state zoom, plus a slow breath so no frame is ever still
      const phase = 2 * Math.PI * t / DUR;
      const z = Z(t) * (1 + 0.045 * Math.sin(2 * phase) + 0.018 * Math.sin(5 * phase + 1.1));
      tf(world, { s: z, x: 40 * Math.sin(phase) + 15 * Math.sin(3 * phase + 0.7),
                  y: 28 * Math.cos(2 * phase) + 11 * Math.cos(5 * phase),
                  r: 1.2 * Math.sin(phase + 0.4) + 0.45 * Math.sin(4 * phase) });

      // content windows: each one enters once the shape is close to its size
      const show = (g, a, bb) => {
        const v = vis(t, b(a), b(bb), 22, 30);
        if (v < 0.02) { tf(g, { o: 0 }); return 0; }
        tf(g, { o: v, blur: (1 - v) * 8, s: lerp(0.94, 1, v) });
        return v;
      };
      show(gBtn, -2.8, 4.6);
      show(gLoad, 4.4, 6.35);
      show(gRing, 6.1, 13.1);
      show(gScore, 13.25, 19.35);
      show(gChart, 19.1, 27.35);
      show(gBands, 27.1, 33.35);
      show(gBr, 33.1, 38.35);
      show(gMkt, 38.1, 43.15);
      show(gToast, 42.9, 47.0);

      // the loader turns while it is on screen
      loadArc.setAttribute('transform', `rotate(${(t * 520).toFixed(1)} 60 60)`);

      // the ring fills to the published probability on a 0 to 40 dial
      const rv = RING(t);
      ringArc.setAttribute('stroke-dashoffset', (CIRC * (1 - clamp(rv / 40, 0, 1))).toFixed(1));
      ringNum.inner.textContent = rv.toFixed(1) + '%';
      tf(ringTick, { o: TICK_O(t) });
      const wv = vis(t, b(11), b(12.5), 24, 30);
      tf(gWatch, { o: wv, y: (1 - wv) * 22 });
      tf(ringCap, { o: vis(t, b(8), b(12.5), 20, 30) });

      // the raw score and its bar
      const sv = SCORE(t);
      scoreNum.inner.textContent = sv.toFixed(1);
      tf(scoreBar, { sx: clamp(sv / 100, 0, 1) });
      const tv = vis(t, b(15.6), b(18.4), 24, 30);
      tf(gTrend, { o: tv, y: (1 - tv) * 18 });

      // the line draws itself, then the average, then the tooltip
      const dv = DRAW(t);
      chartLine.setAttribute('stroke-dashoffset', (CLEN * (1 - dv)).toFixed(1));
      tf(chartBase, { o: vis(t, b(23), b(26.6), 18, 30) });
      tf(chartDot, { o: dv > 0.97 ? 1 : 0, s: dv > 0.97 ? 1 : 0.2 });
      const tipv = vis(t, b(24), b(26.4), 24, 30);
      tf(gTip, { o: tipv, y: (1 - tipv) * 16, s: lerp(0.9, 1, tipv) });
      tf(chartCap, { o: vis(t, b(21.4), b(26.6), 18, 28) });

      // the bars grow out of the baseline they are measured from
      const bv = BARS(t);
      barFill.forEach((el, i) => {
        const k = clamp((bv - i * 0.12) / 0.88, 0, 1);
        tf(el, { sy: Math.max(0.001, k) });
        tf(barNum[i], { o: vis(t, b(29.6 + i * 0.12), b(32.4), 26, 30) });
      });
      const hv = vis(t, b(29), b(32.4), 24, 30);
      tf(gHere, { o: hv, y: (1 - hv) * 20, s: lerp(0.9, 1, hv) });

      // breadth
      brNum.inner.textContent = BRNUM(t).toFixed(1) + '%';
      brLine.setAttribute('stroke-dashoffset', (1400 * (1 - BRDRAW(t))).toFixed(1));
      tf(brCap, { o: vis(t, b(34.8), b(37.4), 22, 30) });

      // the live market row
      const mv = vis(t, b(38.4), b(42.1), 24, 30);
      tf(mktA, { o: mv, y: (1 - mv) * 16 });
      tf(mktB, { o: vis(t, b(38.6), b(42.1), 24, 30), y: (1 - mv) * 16 });
      tf(mktCap, { o: vis(t, b(39), b(42.1), 20, 30) });

      // the cursor, in world coordinates, through the camera
      const [cx, cy] = CUR(t);
      tf(cur, { x: W / 2 + cx * z, y: H / 2 + cy * z, s: PRESS(t), o: CUR_O(t) });
    };
  });
})();
