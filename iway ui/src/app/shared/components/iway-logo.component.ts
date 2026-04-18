import { Component, signal, ChangeDetectionStrategy, NgZone, OnInit, OnDestroy, inject, input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-iway-logo',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg class="logo-svg" viewBox="15 0 235 140" [style.width]="width()" style="height: auto; overflow: visible;"
         (mousemove)="onMouseMove($event)" (mouseleave)="onMouseLeave()">
      <defs>
        <!-- Orb Circular Mask -->
        <clipPath id="circle-clip-logo">
          <circle cx="0" cy="0" r="10" />
        </clipPath>
        <!-- Wave Shape -->
        <path id="pepsi-wave" d="M -15, 0 Q 0, -10 15, -2 L 15, 8 Q 0, -2 -15, 3 Z" />
        <!-- 3D Orb Gradients -->
        <radialGradient id="orb-blue-l" cx="30%" cy="30%" r="70%">
          <stop offset="0%" stop-color="#5fc2e3"/>
          <stop offset="100%" stop-color="#015a77"/>
        </radialGradient>
        <radialGradient id="orb-dark-l" cx="30%" cy="30%" r="70%">
          <stop offset="0%" stop-color="#e8e8e8"/>
          <stop offset="100%" stop-color="#8a8a8a"/>
        </radialGradient>
        <radialGradient id="orb-mid-l" cx="30%" cy="30%" r="70%">
          <stop offset="0%" stop-color="#ffffff"/>
          <stop offset="100%" stop-color="#a1a1a1"/>
        </radialGradient>
        <radialGradient id="orb-light-l" cx="30%" cy="30%" r="70%">
          <stop offset="0%" stop-color="#ffffff"/>
          <stop offset="100%" stop-color="#d9d9d9"/>
        </radialGradient>
      </defs>

      <!-- Blue Sphere -->
      <g class="s-intro s1">
        <g class="s-idle idle-1">
          <!-- Removed CSS transition entirely to prevent fighting with JS Lerp -->
          <g [attr.transform]="'translate(' + (40 + objOffset()[0].x) + ',' + (58 + objOffset()[0].y) + ')'">
            <circle cx="0" cy="0" r="10" fill="url(#orb-blue-l)"/>
            <g clip-path="url(#circle-clip-logo)">
              <use href="#pepsi-wave" transform="rotate(-15)" fill="#95dcf2" />
            </g>
          </g>
        </g>
      </g>
      <!-- Dark Gray Sphere -->
      <g class="s-drop s2">
        <g class="s-idle idle-2">
          <g [attr.transform]="'translate(' + (69 + objOffset()[1].x) + ',' + (58 + objOffset()[1].y) + ')'">
            <circle cx="0" cy="0" r="10" fill="url(#orb-dark-l)"/>
            <g clip-path="url(#circle-clip-logo)">
              <use href="#pepsi-wave" transform="rotate(35)" fill="#f2f2f2" />
            </g>
          </g>
        </g>
      </g>
      <!-- Mid Gray Sphere -->
      <g class="s-drop s3">
        <g class="s-idle idle-3">
          <g [attr.transform]="'translate(' + (98 + objOffset()[2].x) + ',' + (58 + objOffset()[2].y) + ')'">
            <circle cx="0" cy="0" r="10" fill="url(#orb-mid-l)"/>
            <g clip-path="url(#circle-clip-logo)">
              <use href="#pepsi-wave" transform="rotate(95)" fill="#ffffff" />
            </g>
          </g>
        </g>
      </g>
      <!-- Light Gray Sphere -->
      <g class="s-drop s4">
        <g class="s-idle idle-4">
          <g [attr.transform]="'translate(' + (127 + objOffset()[3].x) + ',' + (58 + objOffset()[3].y) + ')'">
            <circle cx="0" cy="0" r="10" fill="url(#orb-light-l)"/>
            <g clip-path="url(#circle-clip-logo)">
              <use href="#pepsi-wave" transform="rotate(-70)" fill="#ffffff" />
            </g>
          </g>
        </g>
      </g>

      <!-- Text: "i-way" -->
      <g clip-path="url(#hide-dot-clip-l)">
        <g class="text-mask">
          <text x="32" y="105" class="iway-main-text"
            [attr.fill]="dark() ? '#ffffff' : '#1a1a1a'">i-way</text>
        </g>
      </g>
      <defs>
        <!-- Expanded X coordinate to 50 to fully cover the remaining dot line -->
        <clipPath id="hide-dot-clip-l">
          <polygon points="0,70 50,70 50,0 350,0 350,160 0,160" />
        </clipPath>
      </defs>

      <!-- Subtitle: "Intelligence Way" -->
      <g class="sub-text-intro">
        <text x="52" y="121" class="iway-sub-text"
          [attr.fill]="dark() ? '#94a3b8' : '#64748b'">Intelligence Way</text>
      </g>
    </svg>
  `,
  styles: [`
    :host { display: inline-flex; align-items: center; }

    .iway-main-text {
      font-family: 'Handel Gothic', 'Segoe UI', sans-serif;
      font-size: 67px;
      letter-spacing: 0px;
      transition: fill 0.4s ease;
    }
    .iway-sub-text {
      font-family: 'Century Gothic Paneuropean', 'Segoe UI', sans-serif;
      font-weight: 300;
      font-size: 14.5px;
      letter-spacing: 0.5px;
      transition: fill 0.4s ease;
    }

    /* Sphere intro animations */
    .s-intro {
      opacity: 0; transform: scale(0);
      animation: sparkPop 0.9s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    }
    .s-drop {
      opacity: 0; transform: translateY(-60px) rotate(-180deg) scale(0.5);
      animation: rollDrop 0.9s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    }
    .s1 { transform-origin: 40px 58px; animation-delay: 0.1s; }
    .s2 { transform-origin: 69px 58px; animation-delay: 0.25s; }
    .s3 { transform-origin: 98px 58px; animation-delay: 0.4s; }
    .s4 { transform-origin: 127px 58px; animation-delay: 0.55s; }

    @keyframes sparkPop {
      0% { transform: scale(0) rotate(-45deg); opacity: 0; }
      60% { transform: scale(1.15) rotate(10deg); opacity: 1; }
      100% { transform: scale(1) rotate(0deg); opacity: 1; }
    }
    @keyframes rollDrop {
      0% { transform: translateY(-60px) rotate(-180deg) scale(0.5); opacity: 0; }
      100% { transform: translateY(0) rotate(0deg) scale(1); opacity: 1; }
    }

    /* Text swipe reveal */
    .text-mask {
      clip-path: polygon(0 0, 0 0, 0 100%, 0 100%);
      animation: swipeRight 1.2s cubic-bezier(0.86, 0, 0.07, 1) forwards;
      animation-delay: 0.4s;
    }
    @keyframes swipeRight {
      0%   { clip-path: polygon(0 0, 0 0, 0 100%, 0 100%); }
      100% { clip-path: polygon(0 0, 110% 0, 110% 100%, 0 100%); }
    }

    /* Subtitle fade-up */
    .sub-text-intro {
      opacity: 0; transform: translateY(15px);
      animation: fadeUp 0.9s cubic-bezier(0.16, 1, 0.3, 1) forwards;
      animation-delay: 0.8s;
    }
    @keyframes fadeUp {
      0% { opacity: 0; transform: translateY(15px); }
      100% { opacity: 1; transform: translateY(0); }
    }

    /* Idle floating */
    .s-idle { animation: floatIdle 3s ease-in-out infinite alternate; }
    .idle-1 { animation-delay: 1.0s; }
    .idle-2 { animation-delay: 1.2s; }
    .idle-3 { animation-delay: 1.4s; }
    .idle-4 { animation-delay: 1.6s; }
    
    @keyframes floatIdle {
      0%   { transform: translateY(0px) scale(1); }
      100% { transform: translateY(-5px) scale(1.02); }
    }
  `]
})
export class IwayLogoComponent implements OnInit, OnDestroy {
  // Use modern signal inputs instead of decorators
  dark = input(true);
  compact = input(false);
  width = input('100%');

  // Angular Signal tracking coordinates
  objOffset = signal([{ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }]);

  // Internal animation state properties for JS Lerping
  private targetOffsets = [{ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }];
  private currentOffsets = [{ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }];
  private animationFrameId?: number;

  // Use the inject() function instead of constructor injection to resolve NG0202 error
  private ngZone = inject(NgZone);

  ngOnInit() {
    // Best Practice: Run high-frequency animations outside Angular to prevent Change Detection lag
    this.ngZone.runOutsideAngular(() => {
      this.animateLerp();
    });
  }

  ngOnDestroy() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
  }

  // Pure mathematical linear interpolation (Lerp) for buttery smoothness
  private animateLerp = () => {
    let needsUpdate = false;

    const newOffsets = this.currentOffsets.map((curr, i) => {
      const target = this.targetOffsets[i];

      // Interpolate 6% of the distance each frame for buttery smoothness (reduced from 12%)
      const nextX = curr.x + (target.x - curr.x) * 0.06;
      const nextY = curr.y + (target.y - curr.y) * 0.06;

      // Check if it's still moving significantly
      if (Math.abs(target.x - curr.x) > 0.01 || Math.abs(target.y - curr.y) > 0.01) {
        needsUpdate = true;
      }

      return { x: nextX, y: nextY };
    });

    if (needsUpdate) {
      this.currentOffsets = newOffsets;
      this.objOffset.set(newOffsets); // Push the perfectly smooth frame to the UI
    }

    this.animationFrameId = requestAnimationFrame(this.animateLerp);
  };

  onMouseMove(e: MouseEvent): void {
    if (this.compact()) return;
    const svg = (e.currentTarget as SVGSVGElement);
    const rect = svg.getBoundingClientRect();

    const scaleX = 235 / rect.width;
    const scaleY = 140 / rect.height;

    const mouseX = (e.clientX - rect.left) * scaleX + 15;
    const mouseY = (e.clientY - rect.top) * scaleY;

    const basePositions = [
      { x: 40, y: 58 }, { x: 69, y: 58 }, { x: 98, y: 58 }, { x: 127, y: 58 }
    ];

    // Only update the "targets". Let the requestAnimationFrame loop handle the physical movement!
    this.targetOffsets = basePositions.map(pos => {
      const dx = mouseX - pos.x;
      const dy = mouseY - pos.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      // Increased pull radius for an even softer, wider magnetic net (prevents fast-mouse snapping)
      const pullRadius = 130;

      if (dist < pullRadius && dist > 1) {
        // Smoother easing curve (1.5) and slightly larger max displacement (10px)
        const pullFactor = Math.pow((1 - dist / pullRadius), 1.5) * 10;
        return { x: (dx / dist) * pullFactor, y: (dy / dist) * pullFactor };
      }
      return { x: 0, y: 0 };
    });
  }

  onMouseLeave(): void {
    // Reset targets. Lerp smoothly slides them back to 0,0 automatically.
    this.targetOffsets = [{ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }];
  }
}