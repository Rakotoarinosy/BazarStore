import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { DashboardStore } from '@/app/core/dashboard/dashboard.store';
import { OrderStatus } from '@/app/core/orders/order-admin.store';
import { ORDER_STATUS, formatAriary, formatRelative } from '../dashboard-format';

@Component({
    standalone: true,
    selector: 'app-recent-sales-widget',
    imports: [CommonModule, RouterModule, TableModule, ButtonModule, TagModule],
    templateUrl: './recentsaleswidget.html'
})
export class RecentSalesWidget {
    readonly stats = inject(DashboardStore).stats;

    statusLabel(status: OrderStatus): string {
        return ORDER_STATUS[status].label;
    }

    statusSeverity(status: OrderStatus) {
        return ORDER_STATUS[status].severity;
    }
    readonly formatAriary = formatAriary;
    readonly formatRelative = formatRelative;
}
