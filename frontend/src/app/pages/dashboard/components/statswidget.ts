import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { DashboardStore } from '@/app/core/dashboard/dashboard.store';
import { formatAriary, formatCompactAriary } from '../dashboard-format';

@Component({
    standalone: true,
    selector: 'app-stats-widget',
    imports: [CommonModule, RouterModule],
    templateUrl: './statswidget.html',
    styles: `
        .dashboard-stat-link {
            color: inherit;
            text-decoration: none;
            transition: box-shadow 0.2s;
        }
        .dashboard-stat-link:hover {
            box-shadow: 0 4px 18px rgb(0 0 0 / 8%);
        }
    `
})
export class StatsWidget {
    readonly dashboard = inject(DashboardStore);
    readonly stats = this.dashboard.stats;
    readonly revenueTrend = this.dashboard.revenueTrend;
    readonly formatAriary = formatAriary;
    readonly formatCompactAriary = formatCompactAriary;
}
