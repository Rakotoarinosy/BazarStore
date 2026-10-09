import { HttpClient } from '@angular/common/http';
import { inject } from '@angular/core';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { Observable, catchError, finalize, forkJoin, map, of, shareReplay, tap } from 'rxjs';

const PRODUCTS_API = '/api/v1/products';
const CATEGORIES_API = '/api/v1/categories';

export interface CatalogProduct {
    id: string;
    code: string;
    name: string;
    description: string;
    price: number;
    quantity: number;
    inventory_status: 'INSTOCK' | 'LOWSTOCK' | 'OUTOFSTOCK';
    image_url: string | null;
    category_id: string;
    category_name: string;
    is_active: boolean;
}

export interface CatalogCategory {
    id: string;
    name: string;
    slug: string;
    description: string;
}

interface CatalogState {
    products: CatalogProduct[];
    categories: CatalogCategory[];
    loading: boolean;
    error: boolean;
}

const initialState: CatalogState = { products: [], categories: [], loading: false, error: false };

export const ProductCatalogStore = signalStore(
    { providedIn: 'root' },
    withState(initialState),
    withMethods((store) => {
        const http = inject(HttpClient);
        let request: Observable<void> | null = null;

        return {
            load(force = false): Observable<void> {
                if (!force && (store.products().length || store.categories().length)) return of(void 0);
                if (request) return request;

                patchState(store, { loading: true, error: false });
                request = forkJoin({
                    products: http.get<CatalogProduct[]>(PRODUCTS_API),
                    categories: http.get<CatalogCategory[]>(CATEGORIES_API)
                }).pipe(
                    tap(({ products, categories }) => patchState(store, { products, categories })),
                    tap({ error: () => patchState(store, { error: true }) }),
                    map(() => void 0),
                    catchError(() => of(void 0)),
                    finalize(() => {
                        request = null;
                        patchState(store, { loading: false });
                    }),
                    shareReplay({ bufferSize: 1, refCount: false })
                );
                return request;
            }
        };
    })
);
