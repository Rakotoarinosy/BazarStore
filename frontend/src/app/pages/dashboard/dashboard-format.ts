import { OrderStatus } from '@/app/core/orders/order-admin.store';

type Severity = 'success' | 'info' | 'warn' | 'danger' | 'secondary' | 'contrast';

export const ORDER_STATUS: Record<OrderStatus, { label: string; severity: Severity }> = {
    pending: { label: 'En attente', severity: 'warn' },
    confirmed: { label: 'Confirmée', severity: 'info' },
    processing: { label: 'En préparation', severity: 'contrast' },
    shipped: { label: 'Expédiée', severity: 'secondary' },
    completed: { label: 'Livrée', severity: 'success' },
    cancelled: { label: 'Annulée', severity: 'danger' }
};

const ariary = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat('fr-FR', { notation: 'compact', maximumFractionDigits: 1 });

export function formatAriary(amount: number): string {
    return `${ariary.format(amount)} Ar`;
}

/** 1 328 000 → « 1,3 M Ar » (graphiques, cartes étroites). */
export function formatCompactAriary(amount: number): string {
    return `${compact.format(amount)} Ar`;
}

/** « à l'instant », « il y a 5 min », « il y a 3 h », puis la date. */
export function formatRelative(value: string): string {
    const minutes = Math.round((Date.now() - new Date(value).getTime()) / 60_000);
    if (minutes < 1) return 'à l’instant';
    if (minutes < 60) return `il y a ${minutes} min`;
    if (minutes < 24 * 60) return `il y a ${Math.round(minutes / 60)} h`;
    return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}
