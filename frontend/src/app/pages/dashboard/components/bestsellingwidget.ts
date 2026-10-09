import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DashboardStore } from '@/app/core/dashboard/dashboard.store';
import { formatAriary } from '../dashboard-format';

/** Une couleur par rang (classes Tailwind écrites en entier pour être générées). */
const COLORS = [
    { bar: 'bg-orange-500', text: 'text-orange-500' },
    { bar: 'bg-cyan-500', text: 'text-cyan-500' },
    { bar: 'bg-pink-500', text: 'text-pink-500' },
    { bar: 'bg-green-500', text: 'text-green-500' },
    { bar: 'bg-purple-500', text: 'text-purple-500' }
];

@Component({
    standalone: true,
    selector: 'app-best-selling-widget',
    imports: [CommonModule],
    templateUrl: './bestsellingwidget.html'
})
export class BestSellingWidget {
    readonly stats = inject(DashboardStore).stats;
    readonly formatAriary = formatAriary;

    color(index: number): { bar: string; text: string } {
        return COLORS[index % COLORS.length];
    }
}
