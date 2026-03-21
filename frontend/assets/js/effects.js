/* ═══════════════════════════════════════════════════════════════════════
   EFFECTS.JS  —  Custom Cursor  +  Typewriter
   Used by: dashboard.html, profile.html

   Drop-in: include effects.css in <head>, effects.js before </body>.
   No external dependencies.
   ═══════════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  /* ════════════════════════════════════════════════════════════════════
     FEATURE 1 — CUSTOM CURSOR
     Architecture:
       • cursor-dot  → snaps to mouse immediately (no lag)
       • cursor-ring → follows via lerp in requestAnimationFrame (soft lag)
     Performance:
       • transform: translate3d()  → GPU composited, no layout/paint
       • CSS transitions only on size/colour props, NOT on transform
       • MutationObserver re-attaches hover listeners on dynamic elements
       • Skipped entirely on touch devices (pointer: coarse)
     ════════════════════════════════════════════════════════════════════ */

  /* ── Guard: touch-only devices don't get a cursor ─────────────────── */
  const isCoarsePointer = window.matchMedia('(pointer: coarse)').matches;
  if (isCoarsePointer) {
    /* Make sure we never hide the system cursor on touch devices */
    document.documentElement.classList.remove('cursor-active');
  } else {
    initCursor();
  }

  function initCursor() {
    /* Signal CSS to hide the system cursor */
    document.documentElement.classList.add('cursor-active');

    /* ── Create DOM elements ─────────────────────────────────────────── */
    const dot  = document.createElement('div');
    const ring = document.createElement('div');
    dot.className  = 'cursor-dot  cursor-hidden';
    ring.className = 'cursor-ring cursor-hidden';
    document.body.appendChild(ring); /* ring behind dot in z-order */
    document.body.appendChild(dot);

    /* ── Position state ──────────────────────────────────────────────── */
    let mouseX = 0, mouseY = 0;   /* target — snaps here instantly      */
    let ringX  = 0, ringY  = 0;   /* current lerped ring position        */
    const LERP = 0.13;            /* 0 = max lag, 1 = instant (like dot) */

    /* ── Mouse tracking ─────────────────────────────────────────────── */
    document.addEventListener('mousemove', function (e) {
      mouseX = e.clientX;
      mouseY = e.clientY;
      /* Dot snaps with zero delay — set transform directly every event */
      dot.style.transform = 'translate3d(' + mouseX + 'px,' + mouseY + 'px,0)';
      dot.classList.remove('cursor-hidden');
      ring.classList.remove('cursor-hidden');
    }, { passive: true });

    document.addEventListener('mouseleave', function () {
      dot.classList.add('cursor-hidden');
      ring.classList.add('cursor-hidden');
    });

    document.addEventListener('mouseenter', function () {
      dot.classList.remove('cursor-hidden');
      ring.classList.remove('cursor-hidden');
    });

    /* ── Click flash ─────────────────────────────────────────────────── */
    document.addEventListener('mousedown', function () {
      dot.classList.add('cursor-click');
      ring.classList.add('cursor-click');
    });
    document.addEventListener('mouseup', function () {
      dot.classList.remove('cursor-click');
      ring.classList.remove('cursor-click');
    });

    /* ── Hover states ────────────────────────────────────────────────── */
    const INTERACTIVE =
      'a, button, [role="button"], label, ' +
      '.btn, .nav-item, .card, .metric-wrap, ' +
      '.user-pill, .topbar-badge, .theme-toggle, ' +
      '.schema-tab, .dropzone, .photo-upload-zone, ' +
      '.avatar-large, .avatar-large-placeholder, ' +
      '.hist-table tbody tr, .profile-merged, ' +
      '.format-tag, .badge, .footer-links a';

    const TEXT_INPUTS = 'input[type=text], input[type=email], input[type=password], textarea';

    function attachHover(el) {
      if (el._cursorHooked) return;
      el._cursorHooked = true;

      const isText = el.matches(TEXT_INPUTS);

      el.addEventListener('mouseenter', function () {
        if (isText) {
          dot.classList.add('cursor-text');
          ring.classList.add('cursor-text');
        } else {
          dot.classList.add('cursor-hover');
          ring.classList.add('cursor-hover');
        }
      });
      el.addEventListener('mouseleave', function () {
        dot.classList.remove('cursor-hover', 'cursor-text');
        ring.classList.remove('cursor-hover', 'cursor-text');
      });
    }

    function attachAll() {
      document.querySelectorAll(INTERACTIVE + ', ' + TEXT_INPUTS).forEach(attachHover);
    }
    attachAll();

    /* Re-attach for dynamically added elements (toasts, dropdowns …) */
    new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        m.addedNodes.forEach(function (node) {
          if (node.nodeType !== 1) return;
          var selector = INTERACTIVE + ', ' + TEXT_INPUTS;
          if (node.matches && node.matches(selector)) attachHover(node);
          if (node.querySelectorAll) node.querySelectorAll(selector).forEach(attachHover);
        });
      });
    }).observe(document.body, { childList: true, subtree: true });

    /* ── rAF loop: smooth ring lag via linear interpolation ──────────── */
    function animateRing() {
      /* Lerp: move ring a fixed fraction toward the mouse each frame */
      ringX += (mouseX - ringX) * LERP;
      ringY += (mouseY - ringY) * LERP;
      ring.style.transform = 'translate3d(' + ringX + 'px,' + ringY + 'px,0)';
      requestAnimationFrame(animateRing);
    }
    requestAnimationFrame(animateRing);
  }

  /* ════════════════════════════════════════════════════════════════════
     FEATURE 2 — TYPEWRITER
     Architecture:
       • Mark any element with  data-typewriter  to activate.
       • Single phrase: types out the element's existing text content.
       • Multiple phrases: supply  data-tw-phrases='["A","B","C"]'
         — each phrase is typed, paused, then deleted before the next.
       • Slight random jitter on delay = natural "human" feel.
       • prefers-reduced-motion → skips animation, shows full text.

     HTML attributes (all optional):
       data-typewriter              — activates the effect
       data-tw-phrases='[…]'       — JSON array of phrases to cycle
       data-tw-speed="60"          — ms per character while typing
       data-tw-delete-speed="30"   — ms per character while deleting
       data-tw-pause="2200"        — ms pause after phrase fully typed
       data-tw-loop="false"        — set false to type once and stop
     ════════════════════════════════════════════════════════════════════ */

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /**
   * Typewriter
   * @param {HTMLElement} el   - target element
   * @param {Object}      opts - configuration (see defaults below)
   */
  function Typewriter(el, opts) {
    opts = opts || {};

    /* Collect phrases: from opts, from data attribute, or from element text */
    var rawPhrases = opts.phrases
      || (el.dataset.twPhrases ? JSON.parse(el.dataset.twPhrases) : null)
      || [el.textContent.trim()];

    this.el          = el;
    this.phrases     = rawPhrases;
    this.speed       = opts.speed       || +el.dataset.twSpeed      || 65;
    this.deleteSpeed = opts.deleteSpeed || +el.dataset.twDeleteSpeed || 32;
    this.pauseTime   = opts.pauseTime   || +el.dataset.twPause      || 2200;
    this.pauseEmpty  = opts.pauseEmpty  || 380;
    this.loop        = (opts.loop !== undefined) ? opts.loop
                     : (el.dataset.twLoop !== 'false')
                     ? (this.phrases.length > 1)   /* auto-loop only if multi-phrase */
                     : false;

    this.phraseIdx = 0;
    this.charIdx   = 0;
    this.deleting  = false;

    /* Build inner structure:
       <el>
         <span class="tw-text">...</span><span class="tw-cursor"></span>
       </el>                                                              */
    el.innerHTML = '';
    this._text   = document.createElement('span');
    this._caret  = document.createElement('span');
    this._caret.className = 'tw-cursor';
    el.appendChild(this._text);
    el.appendChild(this._caret);

    /* Reduced-motion: just show the first phrase, no animation */
    if (reducedMotion) {
      this._text.textContent = this.phrases[0];
      this._caret.classList.add('tw-done');
      return;
    }

    /* Small initial delay so the page has painted before typing starts */
    var self = this;
    setTimeout(function () { self._tick(); }, 320);
  }

  Typewriter.prototype._tick = function () {
    var self   = this;
    var phrase = this.phrases[this.phraseIdx];

    if (!this.deleting) {
      /* ── Typing ───────────────────────────────────────────────────── */
      this.charIdx++;
      this._text.textContent = phrase.slice(0, this.charIdx);

      if (this.charIdx === phrase.length) {
        /* Fully typed — start blinking slowly, then decide next action */
        this._caret.classList.add('tw-done');

        if (this.loop) {
          setTimeout(function () {
            self._caret.classList.remove('tw-done');
            self.deleting = true;
            self._tick();
          }, this.pauseTime);
        }
        /* If not looping, just stay with the caret blinking */
        return;
      }
    } else {
      /* ── Deleting ─────────────────────────────────────────────────── */
      this.charIdx--;
      this._text.textContent = phrase.slice(0, this.charIdx);

      if (this.charIdx === 0) {
        /* Fully deleted — move to next phrase */
        this.deleting  = false;
        this.phraseIdx = (this.phraseIdx + 1) % this.phrases.length;
        setTimeout(function () { self._tick(); }, this.pauseEmpty);
        return;
      }
    }

    /* Schedule next character.
       Math.random() * N adds natural jitter — varies ±50% of base speed. */
    var jitter = this.deleting
      ? this.deleteSpeed + Math.random() * 14
      : this.speed       + Math.random() * 28;

    setTimeout(function () { self._tick(); }, jitter);
  };

  /* ── Auto-initialise every [data-typewriter] on the page ────────────── */
  function initTypewriters() {
    document.querySelectorAll('[data-typewriter]').forEach(function (el) {
      new Typewriter(el);
    });
  }

  /* Run after DOM is ready */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTypewriters);
  } else {
    initTypewriters();
  }

  /* Expose globally for manual use:
       new window.Typewriter(el, { phrases: ['Hello', 'World'], speed: 80 }) */
  window.Typewriter = Typewriter;

})();
