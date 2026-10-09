import { Component, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { DashboardStore, DashboardStats } from '@/app/core/dashboard/dashboard.store';
import { formatAriary, formatRelative } from '../dashboard-format';

type Activity = DashboardStats['activity'][number];

// Classes Tailwind écrites en entier : Tailwind ne génère pas les classes construites dynamiquement.
const KINDS: Record<Activity['kind'], { icon: string; badge: string; text: string }> = {
    new: { icon: 'pi pi-shopping-cart text-blue-500', badge: 'bg-blue-100 dark:bg-blue-400/10', text: 'a passé une commande de' },
    paid: { icon: 'pi pi-credit-card text-green-500', badge: 'bg-green-100 dark:bg-green-400/10', text: 'a payé sa commande de' },
    confirmed: { icon: 'pi pi-check text-cyan-500', badge: 'bg-cyan-100 dark:bg-cyan-400/10', text: 'commande confirmée,' },
    processing: { icon: 'pi pi-box text-purple-500', badge: 'bg-purple-100 dark:bg-purple-400/10', text: 'commande en préparation,' },
    shipped: { icon: 'pi pi-truck text-orange-500', badge: 'bg-orange-100 dark:bg-orange-400/10', text: 'commande expédiée,' },
    completed: { icon: 'pi pi-flag text-teal-500', badge: 'bg-teal-100 dark:bg-teal-400/10', text: 'commande livrée,' },
    cancelled: { icon: 'pi pi-times text-red-500', badge: 'bg-red-100 dark:bg-red-400/10', text: 'commande annulée,' }
};

@Component({
    standalone: true,
    selector: 'app-notifications-widget',
    imports: [CommonModule, RouterModule],
    templateUrl: './notificationswidget.html',
    styles: `
        .dashboard-live-dot {
            width: 0.55rem;
            height: 0.55rem;
            border-radius: 50%;
            background: var(--p-green-500);
            animation: dashboard-live 1.6s ease-in-out infinite;
        }
        @keyframes dashboard-live {
            50% { opacity: 0.3; }
        }
    `
})
export class NotificationsWidget {
    private readonly stats = inject(DashboardStore).stats;
    readonly updatedAt = inject(DashboardStore).updatedAt;

    /** Regroupe l'activité par jour (« Aujourd'hui », « Hier », date). */
    readonly groups = computed(() => {
        const groups: { label: string; items: Activity[] }[] = [];
        for (const item of this.stats()?.activity ?? []) {
            const label = dayLabel(item.at);
            const group = groups.at(-1);
            if (group?.label === label) group.items.push(item);
            else groups.push({ label, items: [item] });
        }
        return groups;
    });

    readonly kinds = KINDS;
    readonly formatAriary = formatAriary;
    readonly formatRelative = formatRelative;
}

function dayLabel(value: string): string {
    const day = new Date(value).toDateString();
    const today = new Date();
    if (day === today.toDateString()) return 'AUJOURD’HUI';
    today.setDate(today.getDate() - 1);
    if (day === today.toDateString()) return 'HIER';
    return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'long' }).format(new Date(value)).toUpperCase();
}
