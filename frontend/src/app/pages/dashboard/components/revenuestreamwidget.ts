import { Component, effect, inject, signal } from '@angular/core';
import { ChartModule } from 'primeng/chart';
import { DashboardStore } from '@/app/core/dashboard/dashboard.store';
import { LayoutService } from '@/app/layout/service/layout.service';
import { formatAriary, formatCompactAriary } from '../dashboard-format';

const MONTH_LABEL = new Intl.DateTimeFormat('fr-FR', { month: 'short', year: '2-digit' });

@Component({
    standalone: true,
    selector: 'app-revenue-stream-widget',
    imports: [ChartModule],
    templateUrl: './revenuestreamwidget.html'
})
export class RevenueStreamWidget {
    private readonly layoutService = inject(LayoutService);
    private readonly stats = inject(DashboardStore).stats;

    readonly chartData = signal<unknown>(null);
    readonly chartOptions = signal<unknown>(null);

    constructor() {
        // Redessine à chaque mise à jour des données (temps réel) ou changement de thème.
        effect(() => {
            const months = this.stats()?.monthly_revenue;
            this.layoutService.layoutConfig().darkTheme;
            // Laisse le thème appliquer ses variables CSS avant de les lire.
            if (months) setTimeout(() => this.initChart(months), 150);
        });
    }

    private initChart(months: { month: string; revenue: number; orders: number }[]): void {
        const style = getComputedStyle(document.documentElement);
        const textColor = style.getPropertyValue('--text-color');
        const borderColor = style.getPropertyValue('--surface-border');
        const mutedColor = style.getPropertyValue('--text-color-secondary');

        this.chartData.set({
            labels: months.map(({ month }) => MONTH_LABEL.format(new Date(`${month}-01T12:00:00`))),
            datasets: [
                {
                    type: 'bar',
                    label: 'Encaissé (Ar)',
                    yAxisID: 'revenue',
                    backgroundColor: style.getPropertyValue('--p-primary-400'),
                    data: months.map(({ revenue }) => revenue),
                    borderRadius: { topLeft: 8, topRight: 8, bottomLeft: 0, bottomRight: 0 },
                    borderSkipped: false,
                    barThickness: 32
                },
                {
                    type: 'line',
                    label: 'Commandes',
                    yAxisID: 'orders',
                    borderColor: style.getPropertyValue('--p-orange-400'),
                    backgroundColor: style.getPropertyValue('--p-orange-400'),
                    data: months.map(({ orders }) => orders),
                    tension: 0.35,
                    pointRadius: 4
                }
            ]
        });

        this.chartOptions.set({
            maintainAspectRatio: false,
            aspectRatio: 0.8,
            plugins: {
                legend: { labels: { color: textColor } },
                tooltip: {
                    callbacks: {
                        label: (context: { dataset: { yAxisID: string; label: string }; parsed: { y: number } }) =>
                            context.dataset.yAxisID === 'revenue' ? `${context.dataset.label} : ${formatAriary(context.parsed.y)}` : `${context.dataset.label} : ${context.parsed.y}`
                    }
                }
            },
            scales: {
                x: { ticks: { color: mutedColor }, grid: { color: 'transparent', borderColor: 'transparent' } },
                revenue: {
                    position: 'left',
                    beginAtZero: true,
                    ticks: { color: mutedColor, callback: (value: number) => formatCompactAriary(value) },
                    grid: { color: borderColor, borderColor: 'transparent', drawTicks: false }
                },
                orders: {
                    position: 'right',
                    beginAtZero: true,
                    ticks: { color: mutedColor, precision: 0 },
                    grid: { drawOnChartArea: false }
                }
            }
        });
    }
}
