(function () {
  'use strict';
  var canvas = document.getElementById('kurai-bg');
  if (!canvas) {
    canvas = document.createElement('canvas');
    canvas.id = 'kurai-bg';
    canvas.setAttribute('aria-hidden', 'true');
    document.body.prepend(canvas);
  }
  var ctx = canvas.getContext('2d');
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var W = 0, H = 0, rafId = null, last = 0;

  var plant = {
    rays: 13,
    leafCount: 5,
    stemColor: '#0f5a3c',
    leafColor: '#0b7a4b',
    leafColor2: '#127a4e',
    flowerColor: '#e8b33c'
  };

  function resize() {
    var dpr = Math.min(window.devicePixelRatio || 1, 1.75);
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function gust(sec) {
    var g = 0.62 + 0.28 * Math.sin(sec * 0.18) + 0.16 * Math.sin(sec * 0.07 + 1.3);
    if (g < 0.35) g = 0.35;
    if (g > 1.15) g = 1.15;
    return g;
  }

  function swayAt(t, sec, g) {
    return (16 * g * t * t * Math.sin(sec * 0.9 + t * 1.4)) +
           (6 * g * t * t * Math.sin(sec * 0.37 + 2.0));
  }

  function draw(sec) {
    var g = gust(sec);
    ctx.clearRect(0, 0, W, H);
    var baseX = W > 820 ? W - 92 : (W > 520 ? W - 64 : W - 46);
    var baseY = H;
    var plantH = H * 0.92;
    var topY = H - plantH;
    var i, t, x, y;

    ctx.beginPath();
    for (i = 0; i <= 24; i++) {
      t = i / 24;
      x = baseX + swayAt(t, sec, g);
      y = baseY - t * plantH;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = plant.stemColor;
    ctx.lineWidth = 7;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();

    var leafT = [0.18, 0.32, 0.46, 0.60, 0.74];
    for (i = 0; i < plant.leafCount; i++) {
      t = leafT[i];
      var side = (i % 2 === 0) ? -1 : 1;
      var sx = baseX + swayAt(t, sec, g);
      var sy = baseY - t * plantH;
      var len = 78 + (i % 3) * 7;
      var tipX = sx + side * len + swayAt(Math.min(1, t + 0.12), sec, g) * 0.6;
      var tipY = sy - 34 - (i % 2) * 8;
      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.quadraticCurveTo(sx + side * len * 0.45, sy - 30, tipX, tipY);
      ctx.quadraticCurveTo(sx + side * len * 0.45, sy + 6, sx, sy);
      ctx.fillStyle = (i % 2 === 0) ? plant.leafColor : plant.leafColor2;
      ctx.fill();
    }

    var cx = baseX + swayAt(1, sec, g);
    var cy = topY;
    for (i = 0; i < plant.rays; i++) {
      var ang = (-90 + (i - 6) * 11) * Math.PI / 180;
      var rayLen = 62 + (i % 3) * 13;
      var wob = Math.sin(sec * 0.9 + i * 0.35) * 7 * g;
      var ex = cx + Math.cos(ang) * rayLen + wob;
      var ey = cy + Math.sin(ang) * rayLen + Math.cos(sec * 0.7 + i * 0.3) * 3 * g;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(ex, ey);
      ctx.strokeStyle = plant.stemColor;
      ctx.lineWidth = 3;
      ctx.lineCap = 'round';
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(ex, ey, 6, 0, Math.PI * 2);
      ctx.fillStyle = plant.flowerColor;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(ex, ey, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = '#9b2c2c';
      ctx.fill();
    }
    ctx.beginPath();
    ctx.arc(cx, cy, 8, 0, Math.PI * 2);
    ctx.fillStyle = plant.flowerColor;
    ctx.fill();
  }

  function frame(ts) {
    if (document.hidden) { rafId = null; return; }
    if (ts - last < 33) { rafId = requestAnimationFrame(frame); return; }
    last = ts;
    draw(ts / 1000);
    rafId = requestAnimationFrame(frame);
  }

  resize();
  window.addEventListener('resize', function () {
    resize();
    if (reduced) draw(0);
  });
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
    } else if (!reduced && rafId === null) {
      last = 0;
      rafId = requestAnimationFrame(frame);
    }
  });

  if (reduced) {
    draw(0);
  } else {
    rafId = requestAnimationFrame(frame);
  }
})();
