// 画布自适应。两种模式：
// 全屏模式（body.fullbleed，产品设计类默认）：画布缩放到正好等于窗口宽（可放大可缩小），像真实产品一样撑满，竖向超出走正常滚动。
// 画布模式（营销类，带衬底和浮层留白）：窗口窄于画布时整体等比缩小，打开即看全图；不放大。
// 用 zoom 而非 transform：zoom 参与布局，缩放后不残留滚动条。截图管线按 1:1 窗口尺寸导出，缩放系数为 1，不影响导出。
(function () {
  function grow(s) {                       // 浮层是绝对定位：量出它探出底图多少，画布底部留出这段
    var body = s.querySelector('.stage-body'), fs = s.querySelectorAll('.stage-body > .mk-float');
    if (!body || !fs.length) return;
    var over = 0;
    fs.forEach(function (f) {
      // 浮层最多七成压在底图上：默认顶在底图四成高处；浮层矮、压得多时往下挪，剩下三成探出底边
      // 左右各一个时错开高度：左下的再往上提一截（最多压住八成），右下的不动，不并排齐平
      f.style.top = ''; f.style.translate = '';
      var bh = body.offsetHeight, fh = f.offsetHeight, top = Math.max(bh * 0.42, bh - fh * 0.7);
      if (fs.length > 1 && f.classList.contains('at-l')) top = Math.max(bh * 0.34, bh - fh * 0.8);
      // 手机浮层是完整一屏真机，比底图矮不了多少：整块上提，大部分压在底图侧边，底边只探出底图下沿约 100
      if (f.classList.contains('mk-float-phone')) top = Math.max(bh * 0.08, bh - fh + 100);
      // 确认弹窗、参数填写页这类小窗：整块落在底图下半截里，离底边留 48，不探出底图
      if (f.classList.contains('mk-float-dlg') && f.classList.contains('mid')) top = Math.max(bh * 0.42, bh - fh - 48);
      f.style.top = Math.round(top) + 'px';
      // 斜放后外接框比浮层本身大，探出的一角可能超出画布：往里收回，导出时不被裁掉
      var fr = f.getBoundingClientRect(), sr = s.getBoundingClientRect(), dx = 0;
      if (fr.right > sr.right - 8) dx = sr.right - 8 - fr.right;
      if (fr.left + dx < sr.left + 8) dx = sr.left + 8 - fr.left;
      if (dx) f.style.translate = Math.round(dx) + 'px 0';
      over = Math.max(over, f.getBoundingClientRect().bottom - body.getBoundingClientRect().bottom);
    });
    s.style.paddingBottom = Math.max(24, Math.ceil(over + 24)) + 'px';
  }

  function fit() {
    var full = document.body.classList.contains('fullbleed');
    var w = document.documentElement.clientWidth - (full ? 0 : 64);
    document.querySelectorAll('.stage').forEach(function (s) {
      s.style.zoom = 1;
      grow(s);
      var k = w / (s.offsetWidth || 1640);   // 按画布实际宽算：PC 1640，手机单屏 520、双屏 1100
      if (!full) k = Math.min(1, k);
      s.style.zoom = k;
    });
  }
  fit();
  addEventListener('resize', fit);
})();
