import { HttpClient } from '@angular/common/http';
import { inject } from '@angular/core';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { Observable, catchError, finalize, of, shareReplay, tap, throwError } from 'rxjs';
import { AuthService } from '../auth/auth.service';

const CATEGORIES_API = '/api/v1/categories';

export interface ProductCategory {
    id: string;
    name: string;
    slug: string;
    description: string;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

export interface CreateProductCategory {
    name: string;
    slug?: string;
    description: string;
    is_active: boolean;
}

export type UpdateProductCategory = Partial<CreateProductCategory>;

interface CategoryAdminState {
    categories: ProductCategory[];
    loaded: boolean;
    loading: boolean;
    ownerId: string | null;
}

const initialState: CategoryAdminState = {
    categories: [],
    loaded: false,
    loading: false,
    ownerId: null
};

export const CategoryAdminStore = signalStore(
    { providedIn: 'root' },
    withState(initialState),
    withMethods((store) => {
        const http = inject(HttpClient);
        const auth = inject(AuthService);
        let listRequest: Observable<ProductCategory[]> | null = null;

        return {
            list(): Observable<ProductCategory[]> {
                const currentUserId = auth.currentUser()?.id ?? null;
                if (store.loaded() && store.ownerId() !== currentUserId) {
                    patchState(store, { categories: [], loaded: false, ownerId: null });
                }
                if (store.loaded()) return of(store.categories());
                if (listRequest) return listRequest;

                patchState(store, { loading: true });
                listRequest = http.get<ProductCategory[]>(`${CATEGORIES_API}/manage`).pipe(
                    tap((categories) => patchState(store, { categories, loaded: true, ownerId: currentUserId })),
                    catchError((error: unknown) => throwError(() => error)),
                    finalize(() => {
                        listRequest = null;
                        patchState(store, { loading: false });
                    }),
                    shareReplay({ bufferSize: 1, refCount: false })
                );
                return listRequest;
            },

            create(category: CreateProductCategory): Observable<ProductCategory> {
                return http.post<ProductCategory>(CATEGORIES_API, category).pipe(
                    tap((created) => {
                        if (store.loaded()) patchState(store, { categories: [...store.categories(), created].sort(byName) });
                    })
                );
            },

            update(id: string, changes: UpdateProductCategory): Observable<ProductCategory> {
                return http.patch<ProductCategory>(`${CATEGORIES_API}/${encodeURIComponent(id)}`, changes).pipe(
                    tap((updated) => {
                        if (store.loaded()) patchState(store, { categories: store.categories().map((category) => category.id === updated.id ? updated : category).sort(byName) });
                    })
                );
            },

            delete(id: string): Observable<void> {
                return http.delete<void>(`${CATEGORIES_API}/${encodeURIComponent(id)}`).pipe(
                    tap(() => {
                        if (store.loaded()) patchState(store, { categories: store.categories().filter((category) => category.id !== id) });
                    })
                );
            }
        };
    })
);

function byName(left: ProductCategory, right: ProductCategory): number {
    return left.name.localeCompare(right.name, 'fr');
}
