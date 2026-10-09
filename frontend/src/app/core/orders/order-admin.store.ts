import { HttpClient, HttpResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { Observable, finalize, firstValueFrom, tap } from 'rxjs';
import { AuthService } from '../auth/auth.service';

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
const OPEN_COUNT_STREAM = `${ORDERS_API}/manage/open-count/stream`;
/** Reconnexion après une erreur : 2 s, 4 s, 8 s… plafonné à 30 s. */
const MAX_RETRY_MS = 30_000;

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
        const auth = inject(AuthService);

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

            /**
             * Compteur du badge « Commandes » en temps réel (Server-Sent Events).
             * `fetch` plutôt qu'EventSource : EventSource ne peut pas envoyer le jeton Bearer.
             * Reconnexion automatique (le serveur ferme le flux toutes les 2 min, jeton renouvelé).
             */
            watchOpenCount(): Observable<number> {
                return new Observable<number>((subscriber) => {
                    let controller: AbortController | null = null;
                    let retryTimer: ReturnType<typeof setTimeout> | undefined;
                    let stopped = false;
                    let failures = 0;

                    const schedule = (delay: number) => {
                        if (!stopped) retryTimer = setTimeout(() => void connect(), delay);
                    };

                    const connect = async (tokenRefreshed = false): Promise<void> => {
                        controller = new AbortController();
                        try {
                            const token = auth.accessToken();
                            const response = await fetch(OPEN_COUNT_STREAM, {
                                headers: { Accept: 'text/event-stream', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
                                credentials: 'include',
                                signal: controller.signal
                            });
                            if (response.status === 401 && !tokenRefreshed) {
                                await firstValueFrom(auth.refresh());
                                return connect(true);
                            }
                            if (response.status === 403) return; // pas un compte de l'équipe : on n'insiste pas
                            if (!response.ok || !response.body) throw new Error(`SSE ${response.status}`);

                            failures = 0;
                            await readServerSentEvents(response.body, (eventName, data) => {
                                if (eventName !== 'open-count') return;
                                const openCount = (JSON.parse(data) as { count: number }).count;
                                patchState(store, { openCount });
                                subscriber.next(openCount);
                            });
                            schedule(500); // fin normale du flux : reconnexion immédiate
                        } catch {
                            if (stopped) return;
                            failures += 1;
                            schedule(Math.min(MAX_RETRY_MS, 1000 * 2 ** failures));
                        }
                    };

                    void connect();
                    return () => {
                        stopped = true;
                        clearTimeout(retryTimer);
                        controller?.abort();
                    };
                });
            },

            downloadInvoice(id: string): Observable<HttpResponse<Blob>> {
                return http.get(`${ORDERS_API}/${encodeURIComponent(id)}/invoice`, { observe: 'response', responseType: 'blob' });
            }
        };
    })
);

/** Lit un flux `text/event-stream` et appelle `onEvent(nom, data)` pour chaque événement. */
async function readServerSentEvents(body: ReadableStream<Uint8Array>, onEvent: (eventName: string, data: string) => void): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
        const { value, done } = await reader.read();
        if (done) return;
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
        let separator: number;
        while ((separator = buffer.indexOf('\n\n')) >= 0) {
            const block = buffer.slice(0, separator);
            buffer = buffer.slice(separator + 2);
            let eventName = 'message';
            const data: string[] = [];
            for (const line of block.split('\n')) {
                if (line.startsWith('event:')) eventName = line.slice(6).trim();
                else if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
                // Les lignes « : ping » (commentaires) et « retry: » sont ignorées.
            }
            if (data.length) onEvent(eventName, data.join('\n'));
        }
    }
}
