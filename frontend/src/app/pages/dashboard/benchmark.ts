import { BenchmarkAxis } from '@/app/core/dashboard/dashboard.store';

/**
 * Ramène chaque axe du radar sur une échelle 0–100 pour comparer des unités différentes
 * (ariary, nombres, %) : sur chaque axe, la meilleure des deux périodes vaut 100.
 * Les pourcentages (taux de livraison) sont déjà sur 0–100 et restent tels quels.
 */
export function normalizeAxis(axis: BenchmarkAxis): { current: number; previous: number } {
    if (axis.unit === 'percent') return { current: axis.current, previous: axis.previous };
    const best = Math.max(axis.current, axis.previous);
    if (best <= 0) return { current: 0, previous: 0 };
    return { current: Math.round((axis.current / best) * 100), previous: Math.round((axis.previous / best) * 100) };
}

/** Évolution en % de la période actuelle par rapport à la précédente (null si pas de référence). */
export function axisTrend(axis: BenchmarkAxis): number | null {
    if (axis.unit === 'percent') return Math.round(axis.current - axis.previous); // écart en points
    if (!axis.previous) return null;
    return Math.round(((axis.current - axis.previous) / axis.previous) * 100);
}
