import { Component, signal, ChangeDetectionStrategy, NgZone, OnInit, OnDestroy, inject, input, ElementRef, viewChild } from '@angular/core';
import { CommonModule } from '@angular/common';

// ─── Orb base positions in SVG coordinates ───
const ORB_BASES = [
  { x: 40, y: 58 },
  { x: 69, y: 58 },
  { x: 98, y: 58 },
  { x: 127, y: 58 },
];
const ZERO4 = () => [{ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }];

@Component({
  selector: 'app-iway-logo',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg #logoSvg class="logo-svg" viewBox="25 30 175 100"
         [style.width]="width()" style="height: auto; overflow: visible; cursor: pointer"
         (mousemove)="onMouseMove($event)" (mouseleave)="onMouseLeave()">
      <defs>
        <!-- Orb Circular Mask -->
        <clipPath id="circle-clip-logo">
          <circle cx="0" cy="0" r="10" />
        </clipPath>

        <!-- Wave Shape with smoother curve -->
        <path id="pepsi-wave" d="M -15, 0 Q 0, -10 15, -2 L 15, 8 Q 0, -2 -15, 3 Z" />

        <!-- 3D Orb Gradients — richer colour stops -->
        <radialGradient id="orb-blue-l" cx="30%" cy="30%" r="70%">
          <stop offset="0%"   stop-color="#7dd3fc"/>
          <stop offset="50%"  stop-color="#38bdf8"/>
          <stop offset="100%" stop-color="#0369a1"/>
        </radialGradient>
        <radialGradient id="orb-dark-l" cx="30%" cy="30%" r="70%">
          <stop offset="0%"   stop-color="#f1f5f9"/>
          <stop offset="50%"  stop-color="#cbd5e1"/>
          <stop offset="100%" stop-color="#64748b"/>
        </radialGradient>
        <radialGradient id="orb-mid-l" cx="30%" cy="30%" r="70%">
          <stop offset="0%"   stop-color="#ffffff"/>
          <stop offset="50%"  stop-color="#e2e8f0"/>
          <stop offset="100%" stop-color="#94a3b8"/>
        </radialGradient>
        <radialGradient id="orb-light-l" cx="30%" cy="30%" r="70%">
          <stop offset="0%"   stop-color="#ffffff"/>
          <stop offset="50%"  stop-color="#f1f5f9"/>
          <stop offset="100%" stop-color="#cbd5e1"/>
        </radialGradient>

        <!-- Mini highlight specular dot for 3D depth -->
        <radialGradient id="specular-dot" cx="35%" cy="25%" r="30%">
          <stop offset="0%"   stop-color="rgba(255,255,255,0.9)"/>
          <stop offset="100%" stop-color="rgba(255,255,255,0)"/>
        </radialGradient>

        <!-- Ambient glow filter for orbs on hover -->
        <filter id="orb-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="blur"/>
          <feMerge>
            <feMergeNode in="blur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>

        <!-- Text clip hides the dot of the 'i' above the orbs -->
        <clipPath id="hide-dot-clip-l">
          <polygon points="0,70 50,70 50,0 350,0 350,160 0,160" />
        </clipPath>
      </defs>

      <!-- ═══ ORBS ═══ -->
      <!-- Blue Sphere -->
      <g class="s-intro s1">
        <g class="s-idle idle-1">
          <g [attr.transform]="orbTransform(0)">
            <circle cx="0" cy="0" r="10" fill="url(#orb-blue-l)" [attr.filter]="isHovering() ? 'url(#orb-glow)' : null"/>
            <g clip-path="url(#circle-clip-logo)">
              <use href="#pepsi-wave" [attr.transform]="waveTransform(0, -15)" fill="#95dcf2" opacity="0.85"/>
            </g>
            <circle cx="-3" cy="-4" r="2.5" fill="url(#specular-dot)"/>
          </g>
        </g>
      </g>

      <!-- Dark Gray Sphere -->
      <g class="s-drop s2">
        <g class="s-idle idle-2">
          <g [attr.transform]="orbTransform(1)">
            <circle cx="0" cy="0" r="10" fill="url(#orb-dark-l)" [attr.filter]="isHovering() ? 'url(#orb-glow)' : null"/>
            <g clip-path="url(#circle-clip-logo)">
              <use href="#pepsi-wave" [attr.transform]="waveTransform(1, 35)" fill="#f2f2f2" opacity="0.85"/>
            </g>
            <circle cx="-3" cy="-4" r="2.5" fill="url(#specular-dot)"/>
          </g>
        </g>
      </g>

      <!-- Mid Gray Sphere -->
      <g class="s-drop s3">
        <g class="s-idle idle-3">
          <g [attr.transform]="orbTransform(2)">
            <circle cx="0" cy="0" r="10" fill="url(#orb-mid-l)" [attr.filter]="isHovering() ? 'url(#orb-glow)' : null"/>
            <g clip-path="url(#circle-clip-logo)">
              <use href="#pepsi-wave" [attr.transform]="waveTransform(2, 95)" fill="#ffffff" opacity="0.85"/>
            </g>
            <circle cx="-3" cy="-4" r="2.5" fill="url(#specular-dot)"/>
          </g>
        </g>
      </g>

      <!-- Light Gray Sphere -->
      <g class="s-drop s4">
        <g class="s-idle idle-4">
          <g [attr.transform]="orbTransform(3)">
            <circle cx="0" cy="0" r="10" fill="url(#orb-light-l)" [attr.filter]="isHovering() ? 'url(#orb-glow)' : null"/>
            <g clip-path="url(#circle-clip-logo)">
              <use href="#pepsi-wave" [attr.transform]="waveTransform(3, -70)" fill="#ffffff" opacity="0.85"/>
            </g>
            <circle cx="-3" cy="-4" r="2.5" fill="url(#specular-dot)"/>
          </g>
        </g>
      </g>

      <!-- ═══ TEXT ═══ -->
      <g clip-path="url(#hide-dot-clip-l)">
        <g class="text-mask">
          <text x="32" y="105" class="iway-main-text"
            [attr.fill]="dark() ? '#ffffff' : '#1a1a1a'">i-way</text>
        </g>
      </g>

      <!-- Subtitle -->
      <g class="sub-text-intro">
        <text x="52" y="121" class="iway-sub-text"
          [attr.fill]="dark() ? '#94a3b8' : '#64748b'">Intelligence Way</text>
      </g>
    </svg>
  `,
  styles: [`
    :host { display: inline-flex; align-items: center; justify-content: center; }

    /* ─── Typography ─── */
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

    /* ─── Sphere Intro: first orb pops in ─── */
    .s-intro {
      opacity: 0; transform: scale(0);
      animation: sparkPop 1.0s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    }
    /* Spheres 2-4 drop from above with bounce */
    .s-drop {
      opacity: 0; transform: translateY(-80px) rotate(-200deg) scale(0.3);
      animation: rollDrop 1.1s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    }

    .s1 { transform-origin: 40px 58px; animation-delay: 0.15s; }
    .s2 { transform-origin: 69px 58px; animation-delay: 0.35s; }
    .s3 { transform-origin: 98px 58px; animation-delay: 0.55s; }
    .s4 { transform-origin: 127px 58px; animation-delay: 0.75s; }

    @keyframes sparkPop {
      0%   { transform: scale(0) rotate(-60deg); opacity: 0; }
      50%  { transform: scale(1.25) rotate(15deg); opacity: 1; }
      75%  { transform: scale(0.95) rotate(-5deg); opacity: 1; }
      100% { transform: scale(1) rotate(0deg); opacity: 1; }
    }

    @keyframes rollDrop {
      0%   { transform: translateY(-80px) rotate(-200deg) scale(0.3); opacity: 0; }
      60%  { transform: translateY(4px) rotate(10deg) scale(1.05); opacity: 1; }
      80%  { transform: translateY(-2px) rotate(-3deg) scale(0.98); opacity: 1; }
      100% { transform: translateY(0) rotate(0deg) scale(1); opacity: 1; }
    }

    /* ─── Text Reveal: sweep right with elastic ease ─── */
    .text-mask {
      clip-path: polygon(0 0, 0 0, 0 100%, 0 100%);
      animation: swipeRight 1.4s cubic-bezier(0.86, 0, 0.07, 1) forwards;
      animation-delay: 0.6s;
    }
    @keyframes swipeRight {
      0%   { clip-path: polygon(0 0, 0 0, 0 100%, 0 100%); }
      100% { clip-path: polygon(0 0, 110% 0, 110% 100%, 0 100%); }
    }

    /* ─── Subtitle: fade + slide up ─── */
    .sub-text-intro {
      opacity: 0; transform: translateY(12px);
      animation: fadeUp 1.0s cubic-bezier(0.16, 1, 0.3, 1) forwards;
      animation-delay: 1.0s;
    }
    @keyframes fadeUp {
      0%   { opacity: 0; transform: translateY(12px); }
      100% { opacity: 1; transform: translateY(0); }
    }

    /* ─── Idle floating: gentle breathe with staggered timing ─── */
    .s-idle {
      animation: floatIdle 4s ease-in-out infinite alternate;
    }
    .idle-1 { animation-delay: 1.2s; }
    .idle-2 { animation-delay: 1.5s; }
    .idle-3 { animation-delay: 1.8s; }
    .idle-4 { animation-delay: 2.1s; }

    @keyframes floatIdle {
      0%   { transform: translateY(0px) scale(1); }
      50%  { transform: translateY(-3px) scale(1.015); }
      100% { transform: translateY(-6px) scale(1.03); }
    }

    /* Reduced motion: respect user preferences */
    @media (prefers-reduced-motion: reduce) {
      .s-intro, .s-drop, .text-mask, .sub-text-intro {
        animation: none !important;
        opacity: 1 !important;
        transform: none !important;
        clip-path: none !important;
      }
      .s-idle { animation: none !important; }
    }
  `]
})
export class IwayLogoComponent implements OnInit, OnDestroy {
  // ─── Inputs ───
  dark = input(true);
  compact = input(false);
  width = input('100%');

  // ─── Signals ───
  objOffset = signal(ZERO4());
  isHovering = signal(false);

  // ─── Internal animation state ───
  private targetOffsets = ZERO4();
  private currentOffsets = ZERO4();
  private velocities = ZERO4();    // for spring physics
  private wavePhases = [0, 0, 0, 0];  // wave rotation additive
  private animationFrameId?: number;
  private ngZone = inject(NgZone);

  // ─── Constants ───
  private readonly PULL_RADIUS = 130;        // how far the gravity reaches
  private readonly MAX_DISPLACEMENT = 10;    // max orb travel distance

  ngOnInit(): void {
    this.ngZone.runOutsideAngular(() => {
      this.tick();
    });
  }

  ngOnDestroy(): void {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
  }

  // ─── Smooth Lerp-based animation loop (Unconditionally Stable) ───
  private tick = (): void => {
    let needsUpdate = false;

    // We process directly into the current array 
    // to maintain performance, and swap if dirty
    const nextOffsets = this.currentOffsets.map((curr, i) => {
      const target = this.targetOffsets[i];

      // Pure Lerp (6% distance per frame) provides buttery tracking
      // that can NEVER overshoot or build explosive glitchy forces
      let nextX = curr.x + (target.x - curr.x) * 0.06;
      let nextY = curr.y + (target.y - curr.y) * 0.06;

      // Animate wave stripe phase based on distance from origin
      const distFromOrigin = Math.sqrt(nextX * nextX + nextY * nextY);
      this.wavePhases[i] = distFromOrigin * 2.5;

      // Precision snapping
      if (Math.abs(target.x - nextX) < 0.02) nextX = target.x;
      if (Math.abs(target.y - nextY) < 0.02) nextY = target.y;

      if (curr.x !== nextX || curr.y !== nextY) {
        needsUpdate = true;
      }

      return { x: nextX, y: nextY };
    });

    if (needsUpdate) {
      this.currentOffsets = nextOffsets;
      this.objOffset.set(nextOffsets);
    }

    this.animationFrameId = requestAnimationFrame(this.tick);
  };

  // ─── Template helpers for transform strings ───
  orbTransform(i: number): string {
    const o = this.objOffset();
    const base = ORB_BASES[i];
    return `translate(${base.x + o[i].x},${base.y + o[i].y})`;
  }

  waveTransform(i: number, baseAngle: number): string {
    return `rotate(${baseAngle + this.wavePhases[i]})`;
  }

  // ─── Mouse interaction ───
  onMouseMove(e: MouseEvent): void {
    if (this.compact()) return;
    this.isHovering.set(true);

    const svg = e.currentTarget as SVGSVGElement;
    const rect = svg.getBoundingClientRect();

    // Map screen coords → SVG viewBox coords (viewBox="25 30 175 100")
    const scaleX = 175 / rect.width;
    const scaleY = 100 / rect.height;
    const mouseX = (e.clientX - rect.left) * scaleX + 25;
    const mouseY = (e.clientY - rect.top) * scaleY + 30;

    this.targetOffsets = ORB_BASES.map(pos => {
      const dx = mouseX - pos.x;
      const dy = mouseY - pos.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < this.PULL_RADIUS) {
        // Squared falloff ensures a silky transition that doesn't jump
        const t = 1 - (dist / this.PULL_RADIUS);
        const pull = t * t * this.MAX_DISPLACEMENT;
        
        // Prevent divison by zero right at epicenter
        const dirX = dist > 0 ? (dx / dist) : 0;
        const dirY = dist > 0 ? (dy / dist) : 0;
        
        return { x: dirX * pull, y: dirY * pull };
      }
      return { x: 0, y: 0 };
    });
  }

  onMouseLeave(): void {
    this.isHovering.set(false);
    this.targetOffsets = ZERO4();
  }
}