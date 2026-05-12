export class PullToRefresh {
  constructor(zones, indicatorId) {
    this.zones = zones;
    this.indicatorId = indicatorId;
    this.startX = 0;
    this.startY = 0;
    this.isPulling = false;
    this.visualY = 0;
    this.THRESHOLD = 60;
    this.MAX_VISUAL_Y = 80;

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
          if (
            e.touches.length === 1 &&
            document.documentElement.scrollTop === 0
          ) {
            this.startX = e.touches[0].clientX;
            this.startY = e.touches[0].clientY;
            this.isPulling = false; // Determine on touchmove
            this.visualY = 0;
          }
        },
        { passive: true },
      );

      zone.addEventListener(
        "touchmove",
        (e) => {
          if (document.documentElement.scrollTop !== 0) return;

          const y = e.touches[0].clientY;
          const x = e.touches[0].clientX;
          const dy = y - this.startY;
          const dx = x - this.startX;

          // Ignore horizontal swipes (tab scrolling) or upward scrolls
          if (Math.abs(dx) > Math.abs(dy) || dy < 0) {
            this.isPulling = false;
            return;
          }

          if (dy > 0) {
            this.isPulling = true;
            // Prevent default only for the vertical pull so native pull to refresh isn't triggered simultaneously
            if (e.cancelable) {
              e.preventDefault();
            }

            // Exponential resistance
            this.visualY = Math.min(dy * 0.4, this.MAX_VISUAL_Y);

            indicator.classList.remove("is-resetting");
            indicator.classList.add("is-pulling");

            // Mid-pull state
            if (this.visualY >= this.THRESHOLD) {
              indicator.classList.add("is-ready");
            } else {
              indicator.classList.remove("is-ready");
            }

            indicator.style.transform = `translateY(${this.visualY}px)`;
            indicator.style.opacity = Math.min(
              this.visualY / this.THRESHOLD,
              1,
            );
          }
        },
        { passive: false },
      );

      zone.addEventListener("touchend", () => {
        if (!this.isPulling) return;
        this.isPulling = false;

        indicator.style.transform = "";
        indicator.style.opacity = "";
        indicator.classList.remove("is-pulling");

        if (this.visualY >= this.THRESHOLD) {
          indicator.classList.remove("is-ready");
          indicator.classList.add("is-loading");

          // Trigger refresh after a tiny delay for animation
          setTimeout(() => {
            globalThis.location.reload();
          }, 300);
        } else {
          indicator.classList.remove("is-ready");
          indicator.classList.add("is-resetting");
        }
      });
    });
  }
}
