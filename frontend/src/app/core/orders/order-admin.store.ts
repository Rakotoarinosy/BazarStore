import { HttpClient, HttpResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { Observable, Subject, filter, finalize, map, share, tap } from 'rxjs';
import { SseClient } from '../realtime/sse-client';

const ORDERS_API = '/api/v1/orders';

export type OrderStatus = 'pending' | 'confirmed' | 'processing' | 'shipped' | 'completed' | 'cancelled';

export interface ManagedOrderItem {
    id: string;
    product_id: string | null;
    product_name: string;
    product_image_url: string | null;
    unit_price: number;
    quantity: number;
    line_total: number;
}

export interface ManagedOrder {
    id: string;
    reference: string;
    user_id: string | null;
    customer_name: string;
    customer_email: string;
    status: OrderStatus;
    total_amount: number;
    created_at: string;
    updated_at: string | null;
    payment_provider: 'stripe' | 'mvola' | null;
    payment_status: 'pending' | 'completed' | 'failed' | null;
    paid_at: string | null;
    invoice_number: string | null;
    items: ManagedOrderItem[];
}

/** Étapes suivantes autorisées (miroir de ORDER_TRANSITIONS côté API). */
export const ORDER_TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
    pending: ['confirmed', 'cancelled'],
    confirmed: ['processing', 'cancelled'],
    processing: ['shipped', 'cancelled'],
    shipped: ['completed'],
    completed: [],
    cancelled: []
};

/** Statuts « ouverts » : ni livrée ni annulée (miroir de OPEN_ORDER_STATUSES côté API). */
const OPEN_STATUSES: OrderStatus[] = ['pending', 'confirmed', 'processing', 'shipped'];
const STAFF_STREAM = `${ORDERS_API}/manage/stream`;

interface OrderAdminState {
    orders: ManagedOrder[];
    loading: boolean;
    openCount: number;
}

const countOpen = (orders: ManagedOrder[]) => orders.filter((order) => OPEN_STATUSES.includes(order.status)).length;

export const OrderAdminStore = signalStore(
    { providedIn: 'root' },
    withState<OrderAdminState>({ orders: [], loading: false, openCount: 0 }),
    withMethods((store) => {
        const http = inject(HttpClient);
        const sse = inject(SseClient);
        const newOrders = new Subject<ManagedOrder>();

        /** Met à jour (ou ajoute en tête) une commande reçue en temps réel. */
        const upsert = (incoming: ManagedOrder): void => {
            const known = store.orders().some((order) => order.id === incoming.id);
            const orders = known ? store.orders().map((order) => (order.id === incoming.id ? incoming : order)) : [incoming, ...store.orders()];
            patchState(store, { orders });
            if (!known) newOrders.next(incoming);
        };

        /**
         * Une seule connexion SSE partagée par tout le backoffice (badge du menu, tableau, détail) :
         * ouverte au premier abonné, fermée quand plus personne n'écoute.
         */
        const realtime$ = sse.stream(STAFF_STREAM).pipe(
            tap((message) => {
                if (message.event === 'open-count') patchState(store, { openCount: (JSON.parse(message.data) as { count: number }).count });
                else if (message.event === 'order') upsert(JSON.parse(message.data) as ManagedOrder);
            }),
            share()
        );

        return {
            // Toujours rechargé : de nouvelles commandes arrivent pendant que l'équipe travaille.
            list(): Observable<ManagedOrder[]> {
                patchState(store, { loading: true });
                return http.get<ManagedOrder[]>(`${ORDERS_API}/manage`).pipe(
                    tap((orders) => patchState(store, { orders, openCount: countOpen(orders) })),
                    finalize(() => patchState(store, { loading: false }))
                );
            },

            updateStatus(id: string, status: OrderStatus): Observable<ManagedOrder> {
                return http.patch<ManagedOrder>(`${ORDERS_API}/${encodeURIComponent(id)}/status`, { status }).pipe(
                    tap((updated) => {
                        const orders = store.orders().map((order) => (order.id === updated.id ? updated : order));
                        // Le badge du menu suit immédiatement le changement de statut.
                        patchState(store, { orders, openCount: countOpen(orders) });
                    })
                );
            },

            /** Temps réel backoffice (SSE) : à garder abonné tant que le backoffice est affiché. */
            watch(): Observable<void> {
                return realtime$.pipe(map(() => undefined));
            },

            /** Commandes qui viennent d'arriver (pour une notification). */
            newOrders(): Observable<ManagedOrder> {
                return newOrders.asObservable().pipe(filter((order) => order.status === 'pending'));
            },

            downloadInvoice(id: string): Observable<HttpResponse<Blob>> {
                return http.get(`${ORDERS_API}/${encodeURIComponent(id)}/invoice`, { observe: 'response', responseType: 'blob' });
            }
        };
    })
);

