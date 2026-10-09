import { Component, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DashboardStore } from '@/app/core/dashboard/dashboard.store';
import { NotificationsWidget } from './components/notificationswidget';
import { StatsWidget } from './components/statswidget';
import { RecentSalesWidget } from './components/recentsaleswidget';
import { BestSellingWidget } from './components/bestsellingwidget';
import { RevenueStreamWidget } from './components/revenuestreamwidget';

@Component({
    selector: 'app-dashboard',
    imports: [StatsWidget, RecentSalesWidget, BestSellingWidget, RevenueStreamWidget, NotificationsWidget],
    templateUrl: './dashboard.html'
})
export class Dashboard {
    constructor() {
        const dashboard = inject(DashboardStore);
        dashboard.load().pipe(takeUntilDestroyed()).subscribe();
        // Temps réel : chaque commande créée, payée ou modifiée recalcule les indicateurs.
        dashboard.watch().pipe(takeUntilDestroyed()).subscribe();
    }
}
