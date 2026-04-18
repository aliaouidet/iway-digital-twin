import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-confidence-gauge',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="relative inline-flex items-center justify-center" [style.width.px]="size" [style.height.px]="size">
      <svg [attr.width]="size" [attr.height]="size" [attr.viewBox]="'0 0 ' + size + ' ' + size" class="transform -rotate-90">
        <!-- Background arc -->
        <circle
          [attr.cx]="center" [attr.cy]="center" [attr.r]="radius"
          fill="none"
          [attr.stroke]="bgColor"
          [attr.stroke-width]="strokeWidth"
          [attr.stroke-dasharray]="circumference"
          [attr.stroke-dashoffset]="0"
          stroke-linecap="round"
          class="opacity-20"
        />
        <!-- Foreground arc (animated) -->
        <circle
          [attr.cx]="center" [attr.cy]="center" [attr.r]="radius"
          fill="none"
          [attr.stroke]="gaugeColor"
          [attr.stroke-width]="strokeWidth"
          [attr.stroke-dasharray]="circumference"
          [attr.stroke-dashoffset]="dashOffset"
          stroke-linecap="round"
          class="transition-all duration-1000 ease-out"
        />
      </svg>
      <!-- Center text -->
      <div class="absolute inset-0 flex flex-col items-center justify-center">
        <span class="font-bold tabular-nums" [style.font-size.px]="size * 0.28" [style.color]="gaugeColor">
          {{value}}
        </span>
        <span class="text-slate-500 font-medium" [style.font-size.px]="size * 0.13">%</span>
      </div>
    </div>
  `,
  styles: [`:host { display: inline-flex; }`]
})
export class ConfidenceGaugeComponent implements OnChanges {
  @Input() value = 0;
  @Input() size = 80;
  @Input() strokeWidth = 6;

  radius = 0;
  center = 0;
  circumference = 0;
  dashOffset = 0;
  gaugeColor = '#10b981';
  bgColor = '#1e293b';

  ngOnChanges(_changes: SimpleChanges): void {
    this.center = this.size / 2;
    this.radius = (this.size - this.strokeWidth) / 2;
    this.circumference = 2 * Math.PI * this.radius;

    // Clamp value between 0 and 100
    const clamped = Math.max(0, Math.min(100, this.value));
    this.dashOffset = this.circumference * (1 - clamped / 100);

    // Color based on confidence level
    if (clamped >= 70) {
      this.gaugeColor = '#10b981'; // emerald
    } else if (clamped >= 40) {
      this.gaugeColor = '#f59e0b'; // amber
    } else {
      this.gaugeColor = '#f43f5e'; // rose
    }
  }
}
