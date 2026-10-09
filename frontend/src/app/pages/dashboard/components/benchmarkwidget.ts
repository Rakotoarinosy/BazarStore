import { Component, computed, effect, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChartModule } from 'primeng/chart';
import { BenchmarkAxis, DashboardStore } from '@/app/core/dashboard/dashboard.store';
import { LayoutService } from '@/app/layout/service/layout.service';
import { axisTrend, normalizeAxis } from '../benchmark';
import { formatAriary } from '../dashboard-format';

@Component({
    standalone: true,
    selector: 'app-benchmark-widget',
    imports: [CommonModule, ChartModule],
    templateUrl: './benchmarkwidget.html'
})
export class BenchmarkWidget {
    private readonly layoutService = inject(LayoutService);
    private readonly stats = inject(DashboardStore).stats;
    readonly axes = computed(() => this.stats()?.benchmark ?? []);

    readonly chartData = signal<unknown>(null);
    readonly chartOptions = signal<unknown>(null);
    readonly trend = axisTrend;

    constructor() {
        // Redessine à chaque mise à jour temps réel des indicateurs ou changement de thème.
        effect(() => {
            const axes = this.axes();
            this.layoutService.layoutConfig().darkTheme;
            if (axes.length) setTimeout(() => this.initChart(axes), 150);
        });
    }

    format(axis: BenchmarkAxis, value: number): string {
        if (axis.unit === 'ariary') return formatAriary(value);
        if (axis.unit === 'percent') return `${value} %`;
        return new Intl.NumberFormat('fr-FR').format(value);
    }

    private initChart(axes: BenchmarkAxis[]): void {
        const style = getComputedStyle(document.documentElement);
        const textColor = style.getPropertyValue('--text-color');
        const borderColor = style.getPropertyValue('--surface-border');
        const normalized = axes.map(normalizeAxis);
        const dataset = (label: string, color: string, data: number[], fill: string) => ({
            label,
            data,
            borderColor: color,
            backgroundColor: fill,
            pointBackgroundColor: color,
            pointBorderColor: color,
            pointHoverBackgroundColor: textColor,
            pointHoverBorderColor: color,
            fill: true
        });

        this.chartData.set({
            labels: axes.map((axis) => axis.label),
            datasets: [
                dataset('Ce mois-ci', style.getPropertyValue('--p-primary-500'), normalized.map((value) => value.current), 'rgba(16, 185, 129, 0.18)'),
                dataset('Mois dernier', style.getPropertyValue('--p-indigo-400'), normalized.map((value) => value.previous), 'rgba(129, 140, 248, 0.12)')
            ]
        });

        this.chartOptions.set({
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: textColor } },
                tooltip: {
                    callbacks: {
                        // Le radar affiche des scores 0–100 ; l'infobulle donne la vraie valeur.
                        label: (context: { datasetIndex: number; dataIndex: number; dataset: { label: string } }) => {
                            const axis = axes[context.dataIndex];
                            const raw = context.datasetIndex === 0 ? axis.current : axis.previous;
                            return `${context.dataset.label} : ${this.format(axis, raw)}`;
                        }
                    }
                }
            },
            scales: {
                r: {
                    min: 0,
                    max: 100,
                    ticks: { display: false, stepSize: 25 },
                    pointLabels: { color: textColor, font: { size: 12 } },
                    grid: { color: borderColor },
                    angleLines: { color: borderColor }
                }
            }
        });
    }
}
