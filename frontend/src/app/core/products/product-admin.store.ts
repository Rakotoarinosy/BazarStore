import { HttpClient } from '@angular/common/http';
import { inject } from '@angular/core';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { Observable, catchError, finalize, of, shareReplay, tap, throwError } from 'rxjs';
import { AuthService } from '../auth/auth.service';

const PRODUCTS_API = '/api/v1/products';

export interface ManagedProduct {
    id: string;
    code: string;
    name: string;
    description: string;
    price: number;
    quantity: number;
    inventory_status: 'INSTOCK' | 'LOWSTOCK' | 'OUTOFSTOCK';
    image_url: string | null;
    image_key: string | null;
    category_id: string;
    category_name: string;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

export interface CreateProduct {
    code: string;
    name: string;
    description: string;
    price: number;
    quantity: number;
    image_url: string | null;
    image_key: string | null;
    category_id: string;
    is_active: boolean;
}

export type UpdateProduct = Partial<CreateProduct>;

export interface ProductImageUpload {
    image_key: string;
    image_url: string;
}

interface ProductAdminState {
    products: ManagedProduct[];
    loaded: boolean;
    loading: boolean;
    ownerId: string | null;
}

const initialState: ProductAdminState = { products: [], loaded: false, loading: false, ownerId: null };

export const ProductAdminStore = signalStore(
    { providedIn: 'root' },
    withState(initialState),
    withMethods((store) => {
        const http = inject(HttpClient);
        const auth = inject(AuthService);
        let listRequest: Observable<ManagedProduct[]> | null = null;

        return {
            list(): Observable<ManagedProduct[]> {
                const currentUserId = auth.currentUser()?.id ?? null;
                if (store.loaded() && store.ownerId() !== currentUserId) {
                    patchState(store, { products: [], loaded: false, ownerId: null });
                }
                if (store.loaded()) return of(store.products());
                if (listRequest) return listRequest;

                patchState(store, { loading: true });
                listRequest = http.get<ManagedProduct[]>(`${PRODUCTS_API}/manage`).pipe(
                    tap((products) => patchState(store, { products, loaded: true, ownerId: currentUserId })),
                    catchError((error: unknown) => throwError(() => error)),
                    finalize(() => {
                        listRequest = null;
                        patchState(store, { loading: false });
                    }),
                    shareReplay({ bufferSize: 1, refCount: false })
                );
                return listRequest;
            },

            create(product: CreateProduct): Observable<ManagedProduct> {
                return http.post<ManagedProduct>(PRODUCTS_API, product).pipe(
                    tap((created) => {
                        if (store.loaded()) patchState(store, { products: [...store.products(), created].sort(byName) });
                    })
                );
            },

            uploadImage(file: File): Observable<ProductImageUpload> {
                const body = new FormData();
                body.append('file', file, file.name);
                return http.post<ProductImageUpload>(`${PRODUCTS_API}/images`, body);
            },

            deleteImage(imageKey: string): Observable<void> {
                return http.delete<void>(`${PRODUCTS_API}/images`, { params: { image_key: imageKey } });
            },

            update(id: string, changes: UpdateProduct): Observable<ManagedProduct> {
                return http.patch<ManagedProduct>(`${PRODUCTS_API}/${encodeURIComponent(id)}`, changes).pipe(
                    tap((updated) => {
                        if (store.loaded()) patchState(store, { products: store.products().map((product) => product.id === updated.id ? updated : product).sort(byName) });
                    })
                );
            },

            delete(id: string): Observable<void> {
                return http.delete<void>(`${PRODUCTS_API}/${encodeURIComponent(id)}`).pipe(
                    tap(() => {
                        if (store.loaded()) patchState(store, { products: store.products().filter((product) => product.id !== id) });
                    })
                );
            }
        };
    })
);

function byName(left: ManagedProduct, right: ManagedProduct): number {
    return left.name.localeCompare(right.name, 'fr');
}
