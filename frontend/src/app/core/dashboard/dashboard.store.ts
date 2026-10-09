import { HttpClient } from '@angular/common/http';
import { computed, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { Observable, debounceTime, finalize, switchMap, tap } from 'rxjs';
import { OrderAdminStore, OrderStatus } from '../orders/order-admin.store';

export interface DashboardStats {
    orders: { total: number; today: number; open: number };
    revenue: { total: number; this_month: number; last_month: number };
    customers: { total: number; new_this_month: number };
    products: { active: number; out_of_stock: number; low_stock: number };
    recent_orders: {
        id: string;
        reference: string;
        customer_name: string;
        total_amount: number;
        status: OrderStatus;
        payment_status: 'pending' | 'completed' | 'failed' | null;
        created_at: string;
        image_url: string | null;
        item_count: number;
    }[];
    monthly_revenue: { month: string; revenue: number; orders: number }[];
    best_sellers: { product_id: string | null; name: string; image_url: string | null; category: string | null; quantity: number; revenue: number; share: number }[];
    activity: {
        order_id: string;
        reference: string;
        kind: 'new' | 'paid' | 'confirmed' | 'processing' | 'shipped' | 'completed' | 'cancelled';
        customer_name: string;
        amount: number;
        at: string;
    }[];
    benchmark: BenchmarkAxis[];
}

/** Axe du radar « ce mois vs mois dernier » (valeurs brutes renvoyées par l'API). */
export interface BenchmarkAxis {
    key: string;
    label: string;
    unit: 'ariary' | 'count' | 'percent';
    current: number;
    previous: number;
}

/** Regroupe les rafales d'événements (paiement + changement de statut…) en un seul rechargement. */
const LIVE_RELOAD_DEBOUNCE_MS = 800;

export const DashboardStore = signalStore(
    { providedIn: 'root' },
    withState<{ stats: DashboardStats | null; loading: boolean; updatedAt: Date | null }>({ stats: null, loading: false, updatedAt: null }),
    withComputed(({ stats }) => ({
        /** Évolution du CA de ce mois par rapport au mois dernier, en % (null si pas de référence). */
        revenueTrend: computed(() => {
            const revenue = stats()?.revenue;
            if (!revenue?.last_month) return null;
            return Math.round(((revenue.this_month - revenue.last_month) / revenue.last_month) * 100);
        })
    })),
    withMethods((store) => {
        const http = inject(HttpClient);
        const orders = inject(OrderAdminStore);

        const load = (): Observable<DashboardStats> => {
            patchState(store, { loading: true });
            return http.get<DashboardStats>('/api/v1/stats/dashboard').pipe(
                tap((stats) => patchState(store, { stats, updatedAt: new Date() })),
                finalize(() => patchState(store, { loading: false }))
            );
        };

        return {
            load,
            /** Recharge les indicateurs à chaque événement temps réel des commandes (flux SSE partagé). */
            watch(): Observable<DashboardStats> {
                return orders.watch().pipe(
                    debounceTime(LIVE_RELOAD_DEBOUNCE_MS),
                    switchMap(() => load())
                );
            }
        };
    })
);
