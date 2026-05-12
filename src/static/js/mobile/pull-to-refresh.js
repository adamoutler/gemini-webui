export class PullToRefresh {
  constructor(zones, indicatorId, options = {}) {
    this.zones = zones;
    this.indicatorId = indicatorId;
    this.options = {
      onRefresh:
        options.onRefresh ||
        (() =>
          new Promise((resolve) => {
            setTimeout(() => {
              globalThis.location.reload();
              resolve();
            }, 300);
          })),
      isAtTop:
        options.isAtTop ||
        (() =>
          window.scrollY === 0 ||
          (document.documentElement.scrollTop === 0 &&
            document.body.scrollTop === 0)),
      threshold: options.threshold || 60,
      maxVisualY: options.maxVisualY || 80,
    };
    this.startX = 0;
    this.startY = 0;
    this.isPulling = false;
    this.visualY = 0;

    this.init();
  }

  init() {
    if (
      typeof document === "undefined" ||
      typeof document.addEventListener !== "function"
    )
      return;

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => this.setup());
    } else {
      this.setup();
    }
  }

  setup() {
    const indicator = document.getElementById(this.indicatorId);
    if (!indicator) return;

    this.zones.forEach((zoneId) => {
      const zone = document.getElementById(zoneId);
      if (!zone) return;

      zone.addEventListener(
        "touchstart",
        (e) => {
          if (e.touches.length !== 1) return;

          this.startX = e.touches[0].clientX;
          this.startY = e.touches[0].clientY;
          this.isPulling = false; // Determine on touchmove
          this.visualY = 0;
        },
        { passive: true },
      );

      zone.addEventListener(
        "touchmove",
        (e) => {
          if (!this.options.isAtTop()) return;

          const y = e.touches[0].clientY;
          const x = e.touches[0].clientX;
          const dy = y - this.startY;
          const dx = x - this.startX;

          // Ignore horizontal swipes or upward scrolls
          if (Math.abs(dx) > Math.abs(dy) || dy <= 0) {
            this.isPulling = false;
            return;
          }

          this.isPulling = true;
          // Prevent default only for the vertical pull so native pull to refresh isn't triggered simultaneously
          if (e.cancelable) {
            e.preventDefault();
          }

          // Exponential resistance
          this.visualY = Math.min(dy * 0.4, this.options.maxVisualY);

          indicator.classList.remove("is-resetting");
          indicator.classList.add("is-pulling");

          // Mid-pull state
          if (this.visualY >= this.options.threshold) {
            indicator.classList.add("is-ready");
          } else {
            indicator.classList.remove("is-ready");
          }

          indicator.style.transform = `translateY(${this.visualY}px)`;
          indicator.style.opacity = Math.min(
            this.visualY / this.options.threshold,
            1,
          );
        },
        { passive: false },
      );

      zone.addEventListener("touchend", async () => {
        if (!this.isPulling) return;
        this.isPulling = false;

        indicator.style.transform = "";
        indicator.style.opacity = "";
        indicator.classList.remove("is-pulling");

        if (this.visualY >= this.options.threshold) {
          indicator.classList.remove("is-ready");
          indicator.classList.add("is-loading");

          try {
            await this.options.onRefresh();
          } finally {
            indicator.classList.remove("is-loading");
            indicator.classList.add("is-resetting");
          }
        } else {
          indicator.classList.remove("is-ready");
          indicator.classList.add("is-resetting");
        }
      });
    });
  }
}
